#!/usr/bin/env python
import mandrill
from model import Withdraw
from blinktrade_withdrawal_protocol import BlinktradeWithdrawalProtocol


class MailerWithdrawalProtocol(BlinktradeWithdrawalProtocol):
  def onConnect(self, response):
    self.mandrill_api = mandrill.Mandrill(self.factory.mandrill_apikey)
    try:
      self.mandrill_api.users.ping()
    except mandrill.Error:
      raise RuntimeError("Invalid Mandrill API key")


  def initiateTransfer(self, process_req_id):
    withdraw_record = Withdraw.get_withdraw_by_process_req_id(self.factory.db_session, process_req_id)
    if withdraw_record.status != '2':
      return

    template_content = []
    withdraw_record_dict = withdraw_record.as_dict()
    for k,v in withdraw_record_dict.iteritems():
      if k in ('amount','paid_amount', 'fixed_fee'):
        v = '{:,.2f}'.format(v / 1e8)
      elif k == 'percent_fee':
        v = float(v)
      elif k == 'created':
        v = v.isoformat()
      template_content.append( { 'name': k, 'content': v  } )
    template_content.append( {'name':'data' , 'content': withdraw_record.data } )


    message = {
      'from_email': self.factory.mandrill_from_email,
      'from_name': self.factory.mandrill_from_name,
      'to': [{'email': self.factory.mandrill_to_email, 
              'name': self.factory.mandrill_to_name, 
              'type': 'to' }],
      'metadata': {'website':  self.factory.mandrill_website },
      'global_merge_vars': template_content
    }

    result = self.mandrill_api.messages.send_template(
      template_name=self.factory.mandrill_template_name,
      template_content=template_content,
      message=message)

    withdraw_record.response = str(result)
    self.factory.db_session.add(withdraw_record)
    self.factory.db_session.commit()

