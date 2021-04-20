import csv
import os
import time
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
import yaml

class ABUploader:

    STATUS_XPATH = "//app-upload-list-page//a[text()='%s']/../following-sibling::div[2]"

    def __init__(self, config, upload_file=None, chrome_options=None, no_login=False):
        self.driver = webdriver.Chrome(chrome_options=chrome_options)
        self.UPLOAD_FILE = upload_file
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
            raise Exception(
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
        campaign_select.find_element(By.TAG_NAME, "input").send_keys(self.CAMPAIGN_NAME)
        time.sleep(1)
        for item in campaign_select.find_elements(By.TAG_NAME, "app-list-item"):
            if item.text == self.CAMPAIGN_NAME:
                item.click()
                break
        # Select People entity type
        entity_select = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, "//mat-select[@placeholder='Entity Type']")))
        entity_select.send_keys('People')

        # driver.find_element(
        #     By.XPATH, "//mat-select[@data-test-id='campaignUploadSelect']").send_keys(self.CAMPAIGN_NAME)
        # Select ID for matching
        ID_SOURCE = (By.XPATH, "//mat-select[@placeholder='Id to use for matching']")
        ID_DEST = (By.XPATH, "//mat-select[@placeholder='Upload Column'][@aria-disabled='false']")
        FIELD_SOURCE = (By.CLASS_NAME, 'mapping__col--source')
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable(ID_SOURCE))
        driver.find_element(*ID_SOURCE).send_keys(self.FIELD_MAP['id']['ab_type'])
        # Map Fields
        print("Mapping %s fields: %s" % (upload_type, self.CAMPAIGN_NAME))
        if 'people' in upload_type:
            col_name = (By.CSS_SELECTOR, '.mapping__col--source input')
            fields = driver.find_elements_by_class_name('mapping')
            for field in fields[:-2]:  # last two are notification and button
                if field.find_elements(*col_name):
                    column = field.find_element(*col_name).get_attribute('value')
                    if column == self.FIELD_MAP['id']['column']:
                        map_to = self.FIELD_MAP['id']['ab_type']
                    else:
                        map_to = self.FIELD_MAP[upload_type].get(column)
                    if map_to:
                        field.find_element(By.TAG_NAME, 'mat-select').send_keys(map_to)
            time.sleep(3)
            driver.find_element(By.XPATH, "//button[contains(text(), 'Process Upload')]").click()

        if 'info' in upload_type:
            WebDriverWait(driver, 5).until(EC.presence_of_element_located(ID_DEST))
            driver.find_element(*ID_DEST).send_keys(self.FIELD_MAP['id']['column'])
            WebDriverWait(driver, 5).until(lambda d: len(d.find_elements(*FIELD_SOURCE)) > 1)
            fields = driver.find_elements(*FIELD_SOURCE)
            for field in fields[1:]:
                col_name = field.find_element(
                    By.TAG_NAME, 'input').get_attribute('value')
                if col_name in self.FIELD_MAP[upload_type]:
                    field_info = self.FIELD_MAP[upload_type][col_name]
                    dest = field.find_element(By.XPATH, './following-sibling::*[2]')
                    dest.find_element(By.TAG_NAME, 'button').click()
                    # Select field
                    driver.find_element(By.XPATH, '//app-field-search-inline//input').send_keys(field_info['name'])
                    try:
                        driver.find_element(By.XPATH, '//app-field-search-inline//mat-list-option').click()
                    except NoSuchElementException:
                        # Clear dialog
                        driver.find_element(By.TAG_NAME, 'body').click()
                    if field_info['type'] == 'notes':
                        driver.find_element(By.XPATH, '//mat-dialog-container//mat-select').send_keys(field_info['note_col'])
                        driver.find_element(By.XPATH, "//mat-dialog-container//button[text()='Apply Field Mapping']").click()
                        time.sleep(1)
            driver.find_element(By.XPATH, '//button[contains(text(),"Next Step")]').click()
            WebDriverWait(driver, 10).until(EC.title_contains('Map to responses'))
            time.sleep(2)
            driver.find_element(By.XPATH, '//button[contains(text(),"Next Step")]').click()
            WebDriverWait(driver, 10).until(EC.title_contains('Create Responses'))
            CONF_LOCATOR = (By.XPATH, '//app-upload-fields-step3-page//button')
            checkboxes = driver.find_elements(
                By.XPATH, '//app-upload-fields-step3-page//mat-checkbox//label')
            if len(checkboxes) > 0:
                print('Creating tags: %s' % self.CAMPAIGN_NAME)
                for checkbox in checkboxes:
                    checkbox.click()
                driver.find_element(*CONF_LOCATOR).click()
                WebDriverWait(driver, 200).until(EC.element_to_be_clickable(CONF_LOCATOR))
            time.sleep(3)
            driver.find_element(*CONF_LOCATOR).click()

        # Make sure the "processing" button worked
        WebDriverWait(driver, 30).until(EC.url_changes(driver.current_url))
        print('---Fields mapped for %s: %s---' % (upload_type, self.CAMPAIGN_NAME))


    def confirm_upload(self, from_list=False):
        driver = self.driver
        # Option 1: Confirm from snackbar right after upload.
        if not from_list:
            # Wait for upload to process
            print("Upload processing...")
            link = WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'snack-bar-container .link'))
            )
            link.click()
            print("Upload processed")
        # Option 2: Confirm from upload list.
        else:
            driver.get(self.BASE_URL + '/admin/upload/list')
            status = WebDriverWait(driver, 20).until(EC.presence_of_element_located(
                (By.XPATH, self.STATUS_XPATH % self.CAMPAIGN_NAME)))
            status.click()
        # Ignore errors
        if 'review' in driver.current_url:
            WebDriverWait(driver, 20).until(EC.element_to_be_clickable(
                (By.LINK_TEXT, 'Continue without re-uploading.'))).click()
        # Confirm upload
        WebDriverWait(driver, 20).until(EC.title_contains('Upload Confirm'))
        for checkbox in driver.find_elements(By.XPATH, '//mat-checkbox//label'):
            checkbox.click()
        driver.find_element(By.CSS_SELECTOR, 'app-upload-confirm button').click()
        print('Confirmed upload, starting now...')


    def get_upload_status(self):
        driver=self.driver
        driver.get(self.BASE_URL + '/admin/upload/list')
        status = WebDriverWait(driver, 20).until(EC.presence_of_element_located(
            (By.XPATH, self.STATUS_XPATH % self.CAMPAIGN_NAME)))
        print("Upload is %s — %s" % (status.text, self.CAMPAIGN_NAME))
        return status.text


    def finish_upload(self):
        driver = self.driver
        # Wait for upload to complete
        STATUS_LOCATOR = (By.XPATH, self.STATUS_XPATH % self.CAMPAIGN_NAME)
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
