#!/usr/bin/env python
import json
import urllib

from functools import partial

from model import Withdraw

from twisted.internet import reactor
from twisted.web.client import getPage

from pyblinktrade.message_builder import MessageBuilder

from blinktrade_withdrawal_protocol import BlinktradeWithdrawalProtocol

class BlocktrailWithdrawalProtocol(BlinktradeWithdrawalProtocol):
  def initiateTransfer(self, process_req_id):
    withdraw_record = Withdraw.get_withdraw_by_process_req_id(self.factory.db_session, process_req_id)
    if withdraw_record.status != '2':
      return


    dest_pay = {}
    dest_pay[json.loads(withdraw_record.data)['Wallet']] = withdraw_record.amount
    print 'paying', dest_pay

    tx_id = self.factory.wallet.pay(dest_pay,
                                    change_address=self.factory.change_address,
                                    allow_zero_conf=True,
                                    randomize_change_idx=True)
    

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
