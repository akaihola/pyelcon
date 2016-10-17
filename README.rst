============================================
 pyelcon - scrape your electric consumption
============================================

Valpas
======

Example::

    from valpas import Valpas
    valpas = Valpas(username='your_email@domain.com',
                    password='your_password',
                    metering_point='1234567')
    valpas.log_in()
    series = valpas.get_hourly_consumption(begin='2016-10-18',
                                           end='2016-10-25')
    series.plot()
