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

    try:
      tx_hash = self.factory.blocktrail_wallet.pay(dest_pay,
                                                   change_address=self.factory.blocktrail_change_address,
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
      withdraw_record.response = str(e)
      self.factory.db_session.add(withdraw_record)
      self.factory.db_session.commit()

      try:
        # send an email to the system administrator
        template_content = [
          {'name': 'NotificationType',  'content': 'HOT_WALLET_SEND_ERROR'},
          {'name': 'WithdrawalProtocol','content': 'Blocktrail'},
          {'name': 'From',              'content': self.factory.blocktrail_change_address},
          {'name': 'To',                'content': json.loads(withdraw_record.data)['Wallet']},
          {'name': 'Amount',            'content': str(withdraw_record.amount)},
          {'name': 'Currency',          'content': 'BTC'},
          {'name': 'Error',             'content': str(e)}
        ]
        message = {
          'from_email': 'noreply@blinktrade.com',
          'from_name': 'No reply',
          'to': [{'email': 'system_motifications@blinktrade.com',
                  'name': 'BlinkTrade system notifications',
                  'type': 'to' }],
          'metadata': {'website':  'https://blinktrade.com/'},
          'global_merge_vars': template_content
        }
        result = self.mandrill_api.messages.send_template(
          template_name='system-notification',
          template_content=template_content,
          message=message)
      except Exception,e:
        print "Error sending the system notification email ", str(e)
