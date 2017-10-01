============================================
 pyelcon - scrape your electric consumption
============================================

.. note:: This scraper stopped working on April 19th, 2017 when Fortum changed
          the authentication mechanism for the Valpas service. Any help for
          fixing the scraper would be appreciated. See `this Twitter thread`_
          for Fortum's response to a request for an API and the plea for help
          with fixing this library.

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


.. _`this twitter thread`: https://twitter.com/akaihola/status/914454180206661632