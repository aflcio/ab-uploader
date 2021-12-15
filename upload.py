import csv
import json
import os
import time
from seleniumwire import webdriver
from seleniumwire.utils import decode
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
import yaml

class ABUploader:

    STATUS_XPATH = "//app-upload-list-page//div[.//child::a|span[text()='%s']]/../div[6]"

    def __init__(self, config, upload_file=None, upload_name=None, chrome_options=None, no_login=False):
        self.driver = webdriver.Chrome(chrome_options=chrome_options)
        self.driver.scopes = ['.*actionbuilder.org/api/graphql']
        self.UPLOAD_FILE = upload_file
        self.UPLOAD_NAME = upload_name
        self.CAMPAIGN_NAME = config['campaign_name']
        self.FIELD_MAP = config['field_map']
        self.BASE_URL = 'https://%s.actionbuilder.org' % config['instance']
        if not no_login: self.login()


    def txt_to_csv(txt_file):
        csv_file = txt_file.replace('.txt', '.csv')
        with open(txt_file, "r") as in_text, open(csv_file, "w") as out_csv:
            # Strip <NUL> characters
            data = (line.replace('\0', '') for line in in_text)
            in_reader = csv.reader(data, delimiter='\t')
            out_writer = csv.writer(out_csv)
            for row in in_reader:
                out_writer.writerow(row)
        return csv_file


    def parse_config(config_path, campaign_key):
        with open(config_path) as file:
            config = yaml.load(file, Loader=yaml.FullLoader)
        if campaign_key not in config:
            raise CampaignError(
                'Could not find campaign %s in config file' % campaign_key)
        return {
            "instance": config['instance'],
            "campaign_name": config[campaign_key]['campaign_name'],
            "field_map": config[campaign_key]['fields']
        }


    def login(self):
        driver = self.driver
        driver.get(self.BASE_URL + '/login')
        LOGIN_OR_HOME = (By.XPATH, '//app-login-box | //app-home')
        el = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located(LOGIN_OR_HOME))
        if el.tag_name == 'app-home':
            print("Already logged in")
            return
        driver.find_element_by_id('email').send_keys(os.getenv('AB_LOGIN'))
        driver.find_element_by_id('password').send_keys(os.getenv('AB_PASSWORD'))
        driver.find_element_by_id('loginButton').click()
        WebDriverWait(driver, 20).until_not(EC.title_contains("Login"))
        print("Logged in succesfully")


    def start_upload(self, upload_type):
        driver = self.driver
        if 'people' in upload_type:
            driver.get(self.BASE_URL + '/admin/upload/entities/mapping')
        if 'info' in upload_type:
            driver.get(self.BASE_URL + '/admin/upload/fields')
        print("Starting %s upload: %s" % (upload_type, self.CAMPAIGN_NAME))
        WebDriverWait(driver, 20).until(EC.title_contains("Upload"))
        # Upload file
        driver.find_element_by_css_selector('input[type="file"]').send_keys(self.UPLOAD_FILE)
        # Select campaign
        campaign_select = driver.find_element(By.CSS_SELECTOR, ".mapping app-campaign-select2")
        campaign_select.click()
        campaign_select.find_element(By.TAG_NAME, "input").send_keys(self.CAMPAIGN_NAME[:5])
        time.sleep(1)
        campaign = next((i for i in campaign_select.find_elements(By.TAG_NAME, "app-list-item") if i.text == self.CAMPAIGN_NAME), None)
        if campaign is None:
            raise CampaignError('Campaign %s not found' % self.CAMPAIGN_NAME)
        campaign.click()
        # Select People entity type
        time.sleep(1)
        entity_select = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//mat-select[@placeholder='Entity Type']")))
        entity_select.send_keys('People')

        ID_SOURCE = (By.XPATH, "//mat-select[@placeholder='Id to use for matching']")
        ID_DEST = (By.XPATH, "//mat-select[@placeholder='Upload Column'][@aria-disabled='false']")
        FIELD_ROWS = (By.CLASS_NAME, 'mapping--tight')
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable(ID_SOURCE))
        driver.find_element(*ID_SOURCE).send_keys(self.FIELD_MAP['id']['ab_type'])
        WebDriverWait(driver, 5).until(EC.presence_of_element_located(ID_DEST))
        driver.find_element(*ID_DEST).send_keys(self.FIELD_MAP['id']['column'])
        time.sleep(1)
        fields = driver.find_elements(*FIELD_ROWS)
        # Map Fields
        print("Mapping %s fields: %s" % (upload_type, self.CAMPAIGN_NAME))
        if 'people' in upload_type:
            for field in fields:
                column = field.find_element(By.TAG_NAME, 'input').get_attribute('value')
                map_to = self.FIELD_MAP[upload_type].get(column)
                if map_to:
                    element = field.find_element(By.TAG_NAME, 'mat-select')
                    self.do_column_map(element, column, map_to)
                    if map_to == 'Email':
                        type_element = field.find_element(By.XPATH, "//mat-select[@placeholder='Email Type']")
                        type_value = self.FIELD_MAP[upload_type].get('email_type')
                        self.do_column_map(type_element, 'Email Type',type_value)
                    if map_to == 'Phone Number':
                        type_element = field.find_element(By.XPATH, "//mat-select[@placeholder='Phone Type']")
                        type_value = self.FIELD_MAP[upload_type].get('phone_type')
                        self.do_column_map(type_element, 'Phone Type', type_value)
            time.sleep(3)
            validation_errors = [e.text for e in driver.find_elements(By.CLASS_NAME, 'error')]
            if validation_errors:
                raise DataError('\n'.join(validation_errors))
            driver.find_element(By.XPATH, "//button[contains(text(), 'Review & Confirm')]").click()
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.XPATH, '//h3[contains(text(), "Review & Process Upload")]')))
            print('---Fields mapped for %s: %s---' % (upload_type, self.CAMPAIGN_NAME))
            for checkbox in driver.find_elements(By.XPATH, '//mat-checkbox//label'):
                checkbox.click()
            button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, '//button[contains(text(),"Process Upload")]')))
            button.click()
            WebDriverWait(driver, 10).until(EC.title_contains('View Uploads'))
            print('---Upload confirmed for %s: %s---' % (upload_type, self.CAMPAIGN_NAME))

        if 'info' in upload_type:
            for field in fields:
                column = field.find_element(By.TAG_NAME, 'input').get_attribute('value')
                if column in self.FIELD_MAP[upload_type]:
                    field_info = self.FIELD_MAP[upload_type][column]
                    element = field.find_element(By.TAG_NAME, 'app-upload-field-selector')
                    self.do_info_map(element, column, field_info)
                    time.sleep(1)
                    if field_info['type'] == 'notes':
                        note_element = driver.find_element(By.XPATH, '//mat-dialog-container//mat-select')
                        self.do_column_map(note_element, column + '_note', field_info.get('note_col'))
                        driver.find_element(By.XPATH, "//mat-dialog-container//button[text()='Apply Field Mapping']").click()
                        time.sleep(1)
                    if field_info['type'] == 'address':
                        elements = driver.find_elements(By.XPATH, '//mat-dialog-container//mat-select')
                        self.do_column_map(elements[0], column + '_street', field_info.get('street_col'))
                        self.do_column_map(elements[1], column + '_city',field_info.get('city_col'))
                        self.do_column_map(elements[2], column + '_state',field_info.get('state_col'))
                        self.do_column_map(elements[3], column + '_zip',field_info.get('zip_col'))
                        self.do_column_map(elements[4], column + '_lat',field_info.get('lat_col'))
                        self.do_column_map(elements[5], column + '_lon',field_info.get('lon_col'))
                        driver.find_element(By.XPATH, "//mat-dialog-container//button[text()='Apply Field Mapping']").click()
                        time.sleep(1)
            print('---Fields mapped for %s: %s---' % (upload_type, self.CAMPAIGN_NAME))
            driver.find_element(By.XPATH, '//button[contains(text(),"Next Step")]').click()
            WebDriverWait(driver, 10).until(EC.title_contains('Map to responses'))
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, 'app-upload-tag-category-map')))
            print('---Responses mapped for %s: %s---' % (upload_type, self.CAMPAIGN_NAME))
            driver.find_element(By.XPATH, '//button[contains(text(),"Next Step")]').click()
            WebDriverWait(driver, 10).until(EC.title_contains('Create Responses'))
            CONF_LOCATOR = (By.XPATH, '//app-upload-fields-step3-page//button')
            if driver.find_element(*CONF_LOCATOR).text == 'Create Responses':
                print('Creating tags: %s' % self.CAMPAIGN_NAME)
                checkboxes = driver.find_elements(By.XPATH, '//app-upload-fields-step3-page//mat-checkbox//label')
                for checkbox in checkboxes:
                    checkbox.click()
                WebDriverWait(driver, 30).until(EC.element_to_be_clickable(CONF_LOCATOR))
                driver.find_element(*CONF_LOCATOR).click()
                WebDriverWait(driver, 300).until(EC.presence_of_element_located((By.XPATH, '//span[text()="Response Creation Results"]')))
            checkboxes = driver.find_elements(By.XPATH, '//app-upload-fields-step3-page//mat-checkbox//label')
            for checkbox in checkboxes:
                checkbox.click()
            WebDriverWait(driver, 30).until(EC.element_to_be_clickable(CONF_LOCATOR))
            driver.find_element(*CONF_LOCATOR).click()
            WebDriverWait(driver, 10).until(EC.title_contains('View Uploads'))
            print('---Responses created for %s: %s---' % (upload_type, self.CAMPAIGN_NAME))

        # Return AB's generated upload nmae
        for req in reversed(driver.requests):
                if json.loads(req.body.decode())['operationName'] == 'CreateUploadMutation':
                    res_data = json.loads(decode(req.response.body, 'gzip').decode())['data']
                    self.UPLOAD_NAME = res_data['createUpload']['upload']['name']
                    return self.UPLOAD_NAME

        # If not found, something went wrong
        raise UploadError("Upload failed to start for %s: %s" % (upload_type, self.CAMPAIGN_NAME))

    def do_column_map(self, element, column, value):
        element.click()
        time.sleep(1)
        options = element.find_elements(By.XPATH, '//mat-option')
        for option in options:
            if option.text == value:
                if 'mat-selected' in option.get_attribute('class'):
                    # Already selected, so clear dropdown
                    self.driver.find_element(By.TAG_NAME, 'body').click()
                else:
                    option.click()
                print('Mapped %s to %s' % (column, value))
                return
        # If no match found, select blank option
        options[0].click()

    def do_info_map(self, element, column, field_info):
        element.click()
        time.sleep(1)
        section_found = False if field_info.get('section') else True
        for option in self.driver.find_elements(By.CSS_SELECTOR, 'mat-list-option, mat-subheader'):
            if not section_found and option.text == field_info.get('section').upper():
                section_found = True
            if option.text == field_info['name'] and section_found:
                option.click()
                print('Mapped %s to %s' % (column, field_info['name']))
                return
        # If no match found, clear the dialog
        self.driver.find_element(By.TAG_NAME, 'body').click()


    def get_upload_status(self):
        driver=self.driver
        driver.get(self.BASE_URL + '/admin/upload/list')
        status = WebDriverWait(driver, 20).until(EC.presence_of_element_located(
            (By.XPATH, self.STATUS_XPATH % self.UPLOAD_NAME)))
        print("Upload is %s — %s" % (status.text, self.CAMPAIGN_NAME))
        return status.text


    def finish_upload(self):
        driver = self.driver
        # Wait for upload to complete
        STATUS_LOCATOR = (By.XPATH, self.STATUS_XPATH % self.UPLOAD_NAME)
        retries = 10
        timeout = 5
        while retries > 0:
            WebDriverWait(driver, 10).until(EC.title_contains("View Uploads"))
            try:
                WebDriverWait(driver, timeout=timeout, poll_frequency=timeout).until(
                    EC.text_to_be_present_in_element(STATUS_LOCATOR, 'Complete'))
                break
            except TimeoutException:
                driver.refresh()
                retries -= 1
                timeout *= 2
                print('Upload in progress. %d retries remaining (%s)' %
                      (retries, self.CAMPAIGN_NAME))
        print("---Upload Complete---")


    def quit(self):
        self.driver.quit()


    def test(self):
        print('Title: %s' % self.driver.title)
        print('URL: %s' % self.driver.current_url)
        print(self.driver.get_log('browser'))

class DataError(Exception):
    pass

class CampaignError(Exception):
    pass

class UploadError(Exception):
    pass
