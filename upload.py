import os
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
import yaml

class ABUploader:

    STATUS_XPATH = "//app-upload-list//a[text()='%s']/../following-sibling::div[2]"

    def __init__(self, config, upload_file=None, chrome_options=None, no_login=False):
        self.driver = webdriver.Chrome(chrome_options=chrome_options)
        self.UPLOAD_FILE = upload_file
        self.CAMPAIGN_NAME = config['campaign_name']
        self.FIELD_MAP = config['field_map']
        self.BASE_URL = 'https://%s.actionbuilder.org' % config['instance']
        if not no_login: self.login()


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
        if upload_type == 'people':
            driver.get(self.BASE_URL + '/admin/upload/people/mapping')
        if upload_type == 'info':
            driver.get(self.BASE_URL + '/admin/upload/tags/mapping')
        print("Starting %s upload" % upload_type)
        WebDriverWait(driver, 20).until(EC.title_contains("Upload"))
        # Upload file
        driver.find_element_by_css_selector('input[type="file"]').send_keys(self.UPLOAD_FILE)
        # Select campaign
        driver.find_element(
            By.XPATH, "//mat-select[@data-test-id='campaignUploadSelect']").send_keys(self.CAMPAIGN_NAME)
        # Select ID for matching
        ID_SOURCE = (By.XPATH, "//mat-select[@placeholder='Id to use for matching']")
        ID_DEST = (By.XPATH, "//mat-select[@placeholder='Upload Column'][@aria-disabled='false']")
        FIELD_SOURCE = (By.CLASS_NAME, 'mapping__col--source')
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable(ID_SOURCE))
        driver.find_element(*ID_SOURCE).send_keys('Custom ID')
        # Map Fields
        print("Mapping fields...")
        if upload_type == 'people':
            col_name = (By.CSS_SELECTOR, '.mapping__col--source input')
            fields = driver.find_elements_by_class_name('mapping')
            for field in fields[:-2]:  # last two are notification and button
                if field.find_elements(*col_name):
                    column = field.find_element(*col_name).get_attribute('value')
                    if column in self.FIELD_MAP[upload_type]:
                        field.find_element(
                            By.TAG_NAME, 'mat-select').send_keys(self.FIELD_MAP[upload_type][column])
            driver.find_element(By.CSS_SELECTOR, '.mapping button').click()
        if upload_type == 'info':
            WebDriverWait(driver, 5).until(EC.presence_of_element_located(ID_DEST))
            driver.find_element(*ID_DEST).send_keys('id')
            WebDriverWait(driver, 5).until(lambda d: len(d.find_elements(*FIELD_SOURCE)) > 1)
            fields = driver.find_elements(*FIELD_SOURCE)
            for field in fields[1:]:
                col_name = field.find_element(
                    By.TAG_NAME, 'input').get_attribute('value')
                if col_name in self.FIELD_MAP[upload_type]:
                    dest = field.find_element(By.XPATH, './following-sibling::*[2]')
                    dest.find_element(By.XPATH, './/mat-select').click()
                    driver.find_element(By.TAG_NAME, 'mat-option') \
                        .send_keys(self.FIELD_MAP[upload_type][col_name]['type'])
                    driver.find_element(By.TAG_NAME, 'mat-option').click()
                    dest.find_element(By.XPATH, './/input') \
                        .send_keys(self.FIELD_MAP[upload_type][col_name]['name'])
                    dest.find_element(By.XPATH, './/ul').click()
                    dest.find_element(By.XPATH, './/ul//ul').click()
            driver.find_element(By.CSS_SELECTOR, '.mapping button').click()
            WebDriverWait(driver, 10).until(EC.title_contains('Map Response'))
            driver.find_element(
                By.XPATH, '//app-upload-tag-categories-mapping/div/div/button').click()
            WebDriverWait(driver, 10).until(EC.title_contains('Upload Confirm'))
            driver.find_element(
                By.XPATH, '//app-upload-tags-confirm-create-tags//button').click()
        print('---Fields mapped for %s upload---' % upload_type)


    def confirm_upload(self):
        driver = self.driver
        # Wait for upload to process
        print("Upload processing...")
        WebDriverWait(driver, 300).until(
            EC.presence_of_element_located((By.TAG_NAME, 'snack-bar-container'))
        )
        driver.find_element(By.CSS_SELECTOR, 'snack-bar-container .link').click()
        print("Upload processed")

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
        print("Upload is %s" % status.text)
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
                print('Upload in progress. %d retries remaining' % retries)
        print("---Upload Complete---")

    def quit(self):
        self.driver.quit()

    def test(self):
        print('Title: %s' % self.driver.title)
        print('URL: %s' % self.driver.current_url)
        print(self.driver.get_log('browser'))
