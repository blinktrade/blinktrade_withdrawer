#!/usr/bin/env python
import json
import argparse
import getpass
import urllib

from urlparse import urlparse
from functools import partial

from model import Base, Withdraw
from sqlalchemy.orm import scoped_session, sessionmaker

from twisted.internet import reactor, ssl
from twisted.web.client import getPage
from autobahn.twisted.websocket import WebSocketClientProtocol, WebSocketClientFactory

from pyblinktrade.message_builder import MessageBuilder
from pyblinktrade.message import JsonMessage


class BtcWithdrawalProtocol(WebSocketClientProtocol):
  def onConnect(self, response):
    print("Server connected: {0}".format(response.peer))

  def sendJSON(self, json_message):
    message = json.dumps(json_message).encode('utf8')
    if self.factory.verbose:
      print 'tx:',message
    self.sendMessage(message)

  def onOpen(self):
    def sendTestRequest():
      self.sendJSON( MessageBuilder.testRequestMessage() )
      self.factory.reactor.callLater(60, sendTestRequest)

    sendTestRequest()

    self.sendJSON( MessageBuilder.login(  self.factory.blintrade_user, self.factory.blintrade_password ) )

  def onMessage(self, payload, isBinary):
    if isBinary:
      print("Binary message received: {0} bytes".format(len(payload)))
      reactor.stop()
      return

    if self.factory.verbose:
      print 'rx:',payload

    msg = JsonMessage(payload.decode('utf8'))
    if msg.isHeartbeat():
      return

    if msg.isUserResponse(): # login response
      if msg.get('UserStatus') != 1:
        reactor.stop()
        raise RuntimeError('Wrong login')

      profile = msg.get('Profile')
      if profile['Type'] != 'BROKER':
        reactor.stop()
        raise RuntimeError('It is not a brokerage account')

      self.factory.broker_username = msg.get('Username')
      self.factory.broker_id = msg.get('UserID')
      self.factory.profile = profile
      return

    if msg.isWithdrawRefresh():
      if msg.get('BrokerID') != self.factory.broker_id:
        return # received a message from a different broker

      msg.set('BrokerUsername', self.factory.broker_username )

      if msg.get('Status') == '1' and msg.get('Currency') == 'BTC':
        withdraw_record = Withdraw.process_withdrawal_refresh_message( self.factory.db_session , msg)
        if withdraw_record:
          process_withdraw_message = MessageBuilder.processWithdraw(action      = 'PROGRESS',
                                                                    withdrawId  = msg.get('WithdrawID'),
                                                                    data        = msg.get('Data') ,
                                                                    percent_fee = msg.get('PercentFee'),
                                                                    fixed_fee   = msg.get('FixedFee') )

          withdraw_record.process_req_id = process_withdraw_message['ProcessWithdrawReqID']

          # sent a B6
          self.sendJSON( process_withdraw_message )
          self.factory.db_session.commit()

    if msg.isProcessWithdrawResponse():
      if not msg.get('Result'):
        return

      process_req_id = msg.get('ProcessWithdrawReqID')
      withdraw_record = Withdraw.get_withdraw_by_process_req_id(self.factory.db_session, process_req_id)

      should_transfer = False
      if withdraw_record:
        if withdraw_record.status == '1' and msg.get('Status') == '2':
          should_transfer = True

        withdraw_record.status = msg.get('Status')
        withdraw_record.reason = msg.get('Reason')
        withdraw_record.reason_id = msg.get('ReasonID')

        self.factory.db_session.add(withdraw_record)
        self.factory.db_session.commit()

        if should_transfer:
          self.factory.reactor.callLater(0, partial(self.initiateBlockchainTransfer, process_req_id) )

  def initiateBlockchainTransfer(self, process_req_id):
    withdraw_record = Withdraw.get_withdraw_by_process_req_id(self.factory.db_session, process_req_id)
    if withdraw_record.status != '2':
      return

    print 'sending {:,.8f} BTC'.format(withdraw_record.amount / 1e8),  'to', json.loads(withdraw_record.data)['Wallet']


    #self.wallet_mnemonic
    # get the public address and the private key from the wallet mnemonic

    #query_args = {
    #  'password'        : self.factory.blockchain_main_password,
    #  'second_password' : self.factory.blockchain_second_password,
    #  'to'              : json.loads(withdraw_record.data)['Wallet'] ,
    #  'amount'          : withdraw_record.amount ,
    #  'from'            : self.factory.from_address,
    #  'note'            : self.factory.note
    #}
    #blockchain_send_payment_url = 'https://blockchain.info/merchant/'\
    #                              + self.factory.blockchain_guid\
    #                              + '/payment?' + urllib.urlencode(query_args)
    #
    #print 'invoking ... ', blockchain_send_payment_url
    #
    #deferred_blockchain_page = getPage( blockchain_send_payment_url )
    #deferred_blockchain_page.addCallback( partial(self.onBlockchainApiSuccessCallback, process_req_id ))
    #deferred_blockchain_page.addErrback( partial(self.onBlockchainApiErrorCallback, process_req_id ) )

  def onBlockchainApiSuccessCallback(self, process_req_id, result):
    withdraw_record = Withdraw.get_withdraw_by_process_req_id(self.factory.db_session, process_req_id)

    result =  json.loads(result)
    if "error" in result:
      withdraw_record.response = result["error"]
      self.factory.db_session.add(withdraw_record)
      self.factory.db_session.commit()

      if result["error"] == "Error Decrypting Wallet":
        reactor.stop()
        raise RuntimeError(result["error"])
      if result["error"] == "pad block corrupted":
        reactor.stop()
        raise RuntimeError(result["error"])
      elif result["error"] == "Second Password Incorrect":
        reactor.stop()
        raise RuntimeError(result["error"])
      elif result["error"] == "Wallet Checksum did not validate. Serious error: Restore a backup if necessary.":
        reactor.stop()
        raise RuntimeError(result["error"])

    elif "tx_hash" in result:
      tx_hash = result["tx_hash"]
      withdraw_data = json.loads(withdraw_record.data)
      withdraw_data['TransactionID'] = tx_hash
      withdraw_data['Currency'] = 'BTC'


      withdraw_record.response = json.dumps(result)
      self.factory.db_session.add(withdraw_record)
      self.factory.db_session.commit()


      process_withdraw_message = MessageBuilder.processWithdraw(action      = 'COMPLETE',
                                                                withdrawId  = withdraw_record.id ,
                                                                data        = withdraw_data )


      self.sendJSON( process_withdraw_message )

    print result


  def onBlockchainApiErrorCallback(self, process_req_id, result):
    withdraw_record = Withdraw.get_withdraw_by_process_req_id(self.factory.db_session, process_req_id)
    withdraw_record.response = str(result)
    self.factory.db_session.add(withdraw_record)
    self.factory.db_session.commit()


    if withdraw_record == '2':
      self.factory.reactor.callLater(15, partial(self.initiateBlockchainTransfer, process_req_id) )

    print result

  def onClose(self, wasClean, code, reason):
    print("WebSocket connection closed: {0}".format(reason))
    reactor.stop()


def main():
  parser = argparse.ArgumentParser(description="Process all withdrawals using blockchain.info wallet api")

  parser.add_argument('-b', "--blinktrade_websocket_url", action="store", dest="blintrade_webscoket_url", help='Blinktrade Websocket Url', type=str)
  parser.add_argument('-u', "--blinktrade_username", action="store", dest="blintrade_user",     help='Blinktrade User', type=str)
  parser.add_argument('-p', "--blinktrade_password", action="store", dest="blintrade_password",  help='Blinktrade Password', type=str)
  parser.add_argument('-db', "--db_engine", action="store", dest="db_engine",  help='Database Engine', type=str)
  parser.add_argument('-v', "--verbose", action="store_true", default=False, dest="verbose",  help='Verbose')

  wallet_mnemonic = getpass.getpass('wallet_mnemonic: ')

  arguments = parser.parse_args()

  if not arguments.db_engine:
    parser.print_help()
    return

  blinktrade_port = 443
  should_connect_on_ssl = True
  blinktrade_url = urlparse(arguments.blintrade_webscoket_url)
  if  blinktrade_url.port is None and blinktrade_url.scheme == 'ws':
    should_connect_on_ssl = False
    blinktrade_port = 80


  db_engine = create_engine(arguments.db_engine, echo=arguments.verbose)
  Base.metadata.create_all(db_engine)


  factory = WebSocketClientFactory(blinktrade_url.geturl())
  factory.blintrade_user = arguments.blintrade_user
  factory.blintrade_password = arguments.blintrade_password
  factory.blockchain_guid = arguments.blockchain_guid
  factory.wallet_mnemonic = wallet_mnemonic
  factory.db_session = scoped_session(sessionmaker(bind=db_engine))
  factory.verbose = arguments.verbose

  factory.protocol = BtcWithdrawalProtocol
  if should_connect_on_ssl:
    reactor.connectSSL( blinktrade_url.netloc ,  blinktrade_port , factory, ssl.ClientContextFactory() )
  else:
    reactor.connectTCP(blinktrade_url.netloc ,  blinktrade_port , factory )

  reactor.run()


if __name__ == '__main__':
  main()
