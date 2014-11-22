#!/usr/bin/env python
import json

from functools import partial

from model import Withdraw

from twisted.internet import reactor
from autobahn.twisted.websocket import WebSocketClientProtocol

from pyblinktrade.message_builder import MessageBuilder
from pyblinktrade.message import JsonMessage


class BlinktradeWithdrawalProtocol(WebSocketClientProtocol):
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

    self.sendJSON( MessageBuilder.login(
      self.factory.blinktrade_broker_id,
      self.factory.blinktrade_user,
      self.factory.blinktrade_password,
      self.factory.blinktrade_2fa) )

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
          self.factory.reactor.callLater(0, partial(self.initiateTransfer, process_req_id) )


  def initiateTransfer(self, process_req_id):
    pass

  def onClose(self, wasClean, code, reason):
    print("WebSocket connection closed: {0}".format(reason))
    reactor.stop()

