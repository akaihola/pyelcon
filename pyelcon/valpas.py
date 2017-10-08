import logging
import time
from urllib.parse import urljoin

import mechanicalsoup
import pandas as pd
import re
import requests

logger = logging.getLogger(__name__)


def milliepoch_utcnow() -> str:
    return str(int(time.time() * 1000))


def format_timestamp(t: str) -> str:
    timestamp = pd.Timestamp(t)
    if not timestamp.tz:
        timestamp = timestamp.tz_localize('UTC')
    return timestamp.strftime('%Y-%m-%dT%H:%M:%S%z')


PORTAL_BASE_URL = 'https://login.fortum.com/portal/'
COUNTRY_FORM_URL = 'https://login.fortum.com/portal/login'


class VerboseSession(requests.Session):
    def send(self,
             request: requests.PreparedRequest, **kwargs) -> requests.Response:
        logger.debug('%s %s', request.method, request.url)
        response = super().send(request, **kwargs)
        logger.debug(response.status_code)
        return response


class StatefulWicketBrowser(mechanicalsoup.StatefulBrowser):
    def open(self, url: str, *args, **kwargs) -> requests.Response:
        enable_meta_refresh = kwargs.pop('enable_meta_refresh', False)
        page = super().open(url, *args, **kwargs)
        if enable_meta_refresh:
            meta_refresh = page.soup.find('meta',
                                          attrs={'http-equiv': 'refresh'})
            if meta_refresh:
                redirect_path = meta_refresh['content'].split('URL=')[1]
                redirect_url = urljoin(page.url, redirect_path)
                return self.open(redirect_url, enable_meta_refresh=True)
        return page

    def submit_selected_ajax(self,
                             focused_element: str,
                             *args, **kwargs) -> requests.Response:
        page = self.get_current_page()
        form = self.get_current_form().form
        focused_element_id = page.find(class_=focused_element).attrs['id']
        self.session.headers.update(
            {'Wicket-Ajax': 'true',
             'Wicket-Ajax-BaseURL': 'login',
             'Wicket-FocusedElementId': focused_element_id,
             'X-Requested-With': 'XMLHttpRequest'})
        form.attrs['action'] = self.get_ajax_url()
        logger.debug('Submitting %s', form.attrs['action'])
        resp = self.submit_selected(*args, **kwargs)
        del self.session.headers['Wicket-Ajax']
        del self.session.headers['Wicket-Ajax-BaseURL']
        del self.session.headers['Wicket-FocusedElementId']
        del self.session.headers['X-Requested-With']
        return resp

    def get_ajax_url(self) -> str:
        pattern = (r'Wicket\.Ajax\.ajax\(\{{"f":"{form[id]}","u":"(.*?)"'
                   .format(form=self.get_current_form().form))
        m = re.search(pattern, str(self.get_current_page()))
        logger.debug('Found %s', m.string[m.start():m.end()])
        path = m.group(1)
        if path.startswith('..'):
            logger.debug('Double period at beginning of path %s - assuming '
                         'one period only', path)
            path = path[1:]
        return urljoin(PORTAL_BASE_URL, path)


class Valpas:
    login_url = 'https://login.fortum.com/portal/login'

    def __init__(self,
                 username: str, password: str,
                 metering_point: str, weather_metering_point: str=None,
                 verbose: bool=False):
        self.username = username
        self.password = password
        self.metering_point = metering_point
        self.weather_metering_point = weather_metering_point
        if verbose:
            self.browser = StatefulWicketBrowser(VerboseSession())
        else:
            self.browser = StatefulWicketBrowser()
        self.logged_in = False
        self._get_response = None  # for debugging
        self._login_response = None  # for debugging
        self.customer_number = None

    def log_in(self):
        self.browser.open(COUNTRY_FORM_URL)
        self.browser.select_form('form')
        self.browser['idpSelectorWrapper:idpSelector'] = '1'
        self.browser['rememberLogin'] = True
        country_response = self.browser.submit_selected_ajax(
            'btn--login-active')
        login_url = urljoin(country_response.url,
                            country_response.headers['Ajax-Location'])
        self.browser.open(login_url)
        self.browser.select_form('form')
        self.browser.submit_selected()
        self.browser.select_form('form')
        self.browser['ttqusername'] = self.username
        self.browser['userPassword'] = self.password
        self.browser.submit_selected_ajax('btn--login')
        login_response = self.browser.open('https://www.fortum.com/valpas/',
                                           enable_meta_refresh=True)
        assert login_response.status_code == 200
        self.logged_in = True
        self._login_response = login_response

        customer_number_response = self.browser.get(
            'https://www.fortum.com/valpas/api/users',
            params={'current': '', '_': milliepoch_utcnow()})
        self.customer_number = customer_number_response.json()['username']

    def get_hourly_consumption(self, begin: str, end: str) -> pd.Series:
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
                    pd.Timedelta(m['utcoffset'], unit='h'),
                    m['values']['EL_ENERGY_CONSUMPTION#0']['value'])
                   for m in response.json()
                   if m['values']]
        df = pd.DataFrame.from_records(
            records, columns=['timestamp', 'utc_offset', 'value'])
        return pd.Series(df.value.values, df.timestamp + df.utc_offset)

    def get_temperature(self, begin: str, end: str):
        if not self.logged_in:
            self.log_in()
        url = ('https://www.fortum.com/valpas/api'
               '/meteringPoints/WEATHER/{}/series'
               .format(self.weather_metering_point))
        response = self.browser.get(
            url,
            params={'_': milliepoch_utcnow(),
                    'customerNumber': self.customer_number,
                    'products': 'WEATHER_TEMPERATURE',
                    'resolution': 'MONTHS_AS_HOURS',
                    'startDate': format_timestamp(begin),
                    'endDate': format_timestamp(end)})
        self._get_response = response
        records = [(pd.Timestamp(m['timestamp']),
                    pd.Timedelta(m['utcoffset'], unit='h'),
                    m['values']['WEATHER_TEMPERATURE#0']['value'])
                   for m in response.json()
                   if m['values']]
        df = pd.DataFrame.from_records(
            records, columns=['timestamp', 'utc_offset', 'value'])
        return pd.Series(df.value.values, df.timestamp + df.utc_offset)
