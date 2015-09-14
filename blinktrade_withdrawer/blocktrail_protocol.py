#!/usr/bin/env python
import json
import urllib

from model import Withdraw

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

    try:
      tx_hash = self.factory.blocktrail_wallet.pay(dest_pay,
                                                   change_address=self.factory.change_address,
                                                   allow_zero_conf=True,
                                                   randomize_change_idx=True)

      withdraw_record.response = tx_hash
      self.factory.db_session.add(withdraw_record)
      self.factory.db_session.commit()

      withdraw_data = json.loads(withdraw_record.data)
      withdraw_data['TransactionID'] = tx_hash
      withdraw_data['Currency'] = 'BTC'

      process_withdraw_message = MessageBuilder.processWithdraw(action      = 'COMPLETE',
                                                                withdrawId  = withdraw_record.id ,
                                                                data        = withdraw_data )
      self.sendJSON( process_withdraw_message )

    except Exception,e:
      print 'Exception', str(e)
      withdraw_record.response = str(e)
      self.factory.db_session.add(withdraw_record)
      self.factory.db_session.commit()


