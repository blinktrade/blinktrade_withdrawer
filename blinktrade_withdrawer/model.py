from sqlalchemy import Column, Integer, String, DateTime, Numeric, Text
from sqlalchemy.ext.declarative import declarative_base


import datetime
import json

Base = declarative_base()
class Withdraw(Base):
  __tablename__   = 'withdraw'
  id              = Column(Integer,       primary_key=True)
  user_id         = Column(Integer,       nullable=False, index=True)
  account_id      = Column(Integer,       nullable=False, index=True)
  broker_id       = Column(Integer,       nullable=False, index=True)
  broker_username = Column(String,        nullable=False, index=True)
  username        = Column(String,        nullable=False, index=True)
  currency        = Column(String,        nullable=False, index=True)
  amount          = Column(Integer,       nullable=False, index=True)
  method          = Column(String,        nullable=False, index=True)
  data            = Column(Text,          nullable=False, index=True)
  client_order_id = Column(String(30),    index=True)
  status          = Column(String(1),     nullable=False, default='0', index=True)
  created         = Column(DateTime,      nullable=False, default=datetime.datetime.now, index=True)
  reason_id       = Column(Integer)
  reason          = Column(String)
  percent_fee     = Column(Numeric,       nullable=False, default=0)
  fixed_fee       = Column(Integer,       nullable=False, default=0)
  paid_amount     = Column(Integer,       nullable=False, default=0, index=True)
  process_req_id  = Column(Integer,       index=True)
  response = Column(Text)

  def as_dict(self):
    import json
    obj = { c.name: getattr(self, c.name) for c in self.__table__.columns }
    obj.update(json.loads(self.data))
    return obj

  @staticmethod
  def get_withdraw_by_id(session, id):
    return session.query(Withdraw).filter_by(id=id).first()

  @staticmethod
  def get_withdraw_by_process_req_id(session, process_req_id):
    return session.query(Withdraw).filter_by(process_req_id=process_req_id).first()


  @staticmethod
  def process_withdrawal_refresh_message(session, msg):
    if msg.get('Status') == "0":
      return  # The user didn't confirm the message yet

    if msg.get('Status') == "1": # User just confirmed the withdrawal
      record = Withdraw.get_withdraw_by_id(session, msg.get('WithdrawID'))
      if record:
        return  # already processed ....

      record = Withdraw( id              = msg.get('WithdrawID'),
                         user_id         = msg.get('UserID'),
                         account_id      = msg.get('UserID'),
                         broker_id       = msg.get('BrokerID'),
                         broker_username = msg.get('BrokerUsername'),
                         username        = msg.get('Username'),
                         currency        = msg.get('Currency'),
                         amount          = msg.get('Amount'),
                         method          = msg.get('Method'),
                         data            = json.dumps(msg.get('Data')),
                         client_order_id = msg.get('ClOrdID'),
                         status          = msg.get('Status'),
                         reason_id       = msg.get('ReasonID'),
                         reason          = msg.get('Reason'),
                         percent_fee     = msg.get('PercentFee'),
                         fixed_fee       = msg.get('FixedFee'),
                         paid_amount     = msg.get('PaidAmount',0),
                         )
      session.add(record)
      return record
