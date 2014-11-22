#!/usr/bin/env python
import json
import urllib

from functools import partial

from model import Withdraw

from twisted.internet import reactor
from twisted.web.client import getPage

from pyblinktrade.message_builder import MessageBuilder

from blinktrade_withdrawal_protocol import BlinktradeWithdrawalProtocol

class BlockchainInfoWithdrawalProtocol(BlinktradeWithdrawalProtocol):
  def initiateTransfer(self, process_req_id):
    withdraw_record = Withdraw.get_withdraw_by_process_req_id(self.factory.db_session, process_req_id)
    if withdraw_record.status != '2':
      return

    print 'sending {:,.8f} BTC'.format(withdraw_record.amount / 1e8),  'to', json.loads(withdraw_record.data)['Wallet']

    query_args = [
      ('password'        , self.factory.blockchain_main_password),
      ('second_password' , self.factory.blockchain_second_password),
      ('to'              , json.loads(withdraw_record.data)['Wallet']),
      ('amount'          , withdraw_record.amount),
      ('from'            , self.factory.from_address),
      ('note'            , self.factory.note)
    ]
    blockchain_send_payment_url = 'https://blockchain.info/merchant/'\
                                  + self.factory.blockchain_guid\
                                  + '/payment?' + urllib.urlencode(query_args)
    print 'invoking ... ', blockchain_send_payment_url

    deferred_blockchain_page = getPage( blockchain_send_payment_url )
    deferred_blockchain_page.addCallback( partial(self.onBlockchainApiSuccessCallback, process_req_id ))
    deferred_blockchain_page.addErrback( partial(self.onBlockchainApiErrorCallback, process_req_id ) )

  def onBlockchainApiSuccessCallback(self, process_req_id, result):
    withdraw_record = Withdraw.get_withdraw_by_process_req_id(self.factory.db_session, process_req_id)

    result =  json.loads(result)
    if "error" in result:
      withdraw_record.blockchain_response = result["error"]
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


      withdraw_record.blockchain_response = json.dumps(result)
      self.factory.db_session.add(withdraw_record)
      self.factory.db_session.commit()

      process_withdraw_message = MessageBuilder.processWithdraw(action      = 'COMPLETE',
                                                                withdrawId  = withdraw_record.id ,
                                                                data        = withdraw_data )

      self.sendJSON( process_withdraw_message )

    print result


  def onBlockchainApiErrorCallback(self, process_req_id, result):
    withdraw_record = Withdraw.get_withdraw_by_process_req_id(self.factory.db_session, process_req_id)
    withdraw_record.blockchain_response = str(result)
    self.factory.db_session.add(withdraw_record)
    self.factory.db_session.commit()


    if withdraw_record == '2':
      self.factory.reactor.callLater(15, partial(self.initiateBlockchainTransfer, process_req_id) )

    print result
