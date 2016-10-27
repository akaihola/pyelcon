import mechanicalsoup
import time
import pandas as pd


def milliepoch_utcnow():
    return str(int(time.time() * 1000))


def format_timestamp(t):
    timestamp = pd.Timestamp(t)
    if not timestamp.tz:
        timestamp = timestamp.tz_localize('UTC')
    return timestamp.strftime('%Y-%m-%dT%H:%M:%S%z')


class Valpas:
    login_url = 'https://www.fortum.com/EAIWebFI_PROD/login.jsp?original_url=%2Fvalpas%2F&langId=0'

    def __init__(self, username, password, metering_point):
        self.username = username
        self.password = password
        self.metering_point = metering_point
        self.browser = mechanicalsoup.Browser()
        self.logged_in = False

    def log_in(self):
        login_page = self.browser.get(self.login_url)
        login_form = login_page.soup.select_one('form#registration')
        login_form.select_one('input[name=username]')['value'] = self.username
        login_form.select_one('input[name=password]')['value'] = self.password
        login_form.attrs['method'] = 'POST'
        login_response = self.browser.submit(login_form,
                                             'https://www.fortum.com/EAIWebFI_PROD/LoginServlet',
                                             headers={'Referer': self.login_url})
        assert login_response.status_code == 200
        self.logged_in = True
        self._login_response = login_response

        customer_number_response = self.browser.get(
            'https://www.fortum.com/valpas/api/users',
            params={'current': '', '_': milliepoch_utcnow()})
        self.customer_number = customer_number_response.json()['username']

    def get_hourly_consumption(self, begin, end):
        if not self.logged_in:
            self.log_in()
        url = ('https://www.fortum.com/valpas/api/meteringPoints/ELECTRICITY/{}/series'
               .format(self.metering_point))
        response = self.browser.get(
            url,
            params={'_': milliepoch_utcnow(),
                    'customerNumber': self.customer_number,
                    'products': 'EL_ENERGY_CONSUMPTION',
                    'resolution': 'MONTHS_AS_HOURS',
                    'startDate': format_timestamp(begin),
                    'endDate': format_timestamp(end)})
        self._get_response = response
        records = [(pd.Timestamp(m['timestamp']),
                    pd.Timedelta(m['UTCOffset'], unit='h'),
                    m['values']['EL_ENERGY_CONSUMPTION#0']['value'])
                   for m in response.json()
                   if m['values']]
        df = pd.DataFrame.from_records(records,
                                       columns=['timestamp', 'utc_offset', 'value'])
        return pd.Series(df.value.values,
                         df.timestamp + df.utc_offset)
