from __future__ import division

import argparse
import codecs
from collections import defaultdict
import json
import os
import re
import sys
import time
from utils.crawling_utils import pandas_utils
import shutil
from align.predict import face_detect_crawling
import cv2
import tensorflow as tf
import align.detect_face as detect_face
try:
    from urlparse import urljoin
    from urllib import urlretrieve
except ImportError:
    from urllib.parse import urljoin
    from urllib.request import urlretrieve

import datetime
import pandas as pd
import math
import requests
import selenium
from selenium import webdriver
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from bs4 import BeautifulSoup

import logging

import cv2

#import tensormsa_insightface.src.common.predict as predict
import align.deploy.face_embedding as face_embedding
import align.deploy.face_preprocess as face_preprocess
#from tensormsa_insightface import init_value


# HOST
WEBBRIVER_CHROME_PATH = '/home/dev/insta_crawling/chromedriver'
HOST = 'https://www.instagram.com'
#_1cr2e
# SELENIUM CSS SELECTOR
CSS_LOAD_MORE = "a._1cr2e._epyes"
CLASS_LOAD_MORE = "_1cr2e._epyes"
#CSS_RIGHT_ARROW = "a[class='_de018 coreSpriteRightPaginationArrow']"
CSS_RIGHT_ARROW = "a[class='_3a693 coreSpriteRightPaginationArrow']"
#                            _3a693 coreSpriteRightPaginationArrow
CSS_DETAIL_POPUP ="div._mck9w._gvoze._f2mse"
#FIREFOX_FIRST_POST_PATH = "//div[contains(@class, '_8mlbc _vbtk2 _t5r8b')]"
#FIREFOX_FIRST_POST_PATH = "//div[contains(@class, '_mck9w _gvoze _f2mse')]"
FIREFOX_FIRST_POST_PATH = "//div[contains(@class, '_mck9w')]"
FIREFOX_FIRST_POST_HASH_PATH = "//div[contains(@class, '_8mlbc _vbtk2 _t5r8b')]"
TIME_TO_CAPTION_PATH = "../../../div/ul/li/span"

# FOLLOWERS/FOLLOWING RELATED
CSS_EXPLORE = "a[href='/explore/']"
CSS_LOGIN = "a[href='/accounts/login/']"
CSS_FOLLOWERS = "a[href='/{}/followers/']"
CSS_FOLLOWING = "a[href='/{}/following/']"
FOLLOWER_PATH = "//div[contains(text(), 'Followers')]"
FOLLOWING_PATH = "//div[contains(text(), 'Following')]"

# JAVASCRIPT COMMANDS
SCROLL_UP = "window.scrollTo(0, 0);"
SCROLL_DOWN = "window.scrollTo(0, document.body.scrollHeight);"

MASTER_DATA_PATH = './master_data'
MASTER_DATA_FILE = 'crowling_master_data.csv'
MASTER_DATA_BACKUP = './master_data/backup'
MASTER_DATA_COLUMN_LIST = ['id', 'ModifyDatetime', 'ActiveFlag', 'Crawling_time',  'Total_post']


EXCEPT_DATA_PATH = './except_data'
EXCEPT_DATA_FILE = 'crowling_except_data.csv'

class url_change(object):
    """
        Used for caption scraping
    """
    def __init__(self, prev_url):
        self.prev_url = prev_url

    def __call__(self, driver):
        return self.prev_url != driver.current_url

class InstagramCrawler(object):
    """
        Crawler class
    """
    def __init__(self, headless=True, firefox_path=None, firefox=True):
        if headless:
            print("headless mode on")

            options = webdriver.ChromeOptions()
            options.add_argument('headless')
            options.add_argument('window-size=1920x1080')
            options.add_argument("disable-gpu")

            # binary = FirefoxBinary(firefox_path)
            self._driver = webdriver.Chrome(WEBBRIVER_CHROME_PATH, chrome_options=options)

        else:
            if firefox :

                binary = FirefoxBinary(firefox_path)
                self._driver = webdriver.Firefox(firefox_binary=binary)
            else:

                #binary = FirefoxBinary(firefox_path)
                self._driver = webdriver.Chrome(WEBBRIVER_CHROME_PATH)


        self.data = defaultdict(list)
        self.current_df = pd.DataFrame()

    def login(self, authentication=None):
        """
            authentication: path to authentication json file
        """
        self._driver.get(urljoin(HOST, "accounts/login/"))

        if authentication:
            print("Username and password loaded from {}".format(authentication))
            with open(authentication, 'r') as fin:
                auth_dict = json.loads(fin.read())
            # Input username
            username_input = WebDriverWait(self._driver, 5).until(
                EC.presence_of_element_located((By.NAME, 'username'))
            )
            username_input.send_keys(auth_dict['username'])
            # Input password
            password_input = WebDriverWait(self._driver, 5).until(
                EC.presence_of_element_located((By.NAME, 'password'))
            )
            password_input.send_keys(auth_dict['password'])
            # Submit
            password_input.submit()
        else:
            print("Type your username and password by hand to login!")
            print("You have a minute to do so!")

        print("")
        WebDriverWait(self._driver, 60).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, CSS_EXPLORE))
        )

    def quit(self):
        self._driver.quit()

    def crawl(self, dir_prefix, query, crawl_type, number, caption, authentication):
        print("dir_prefix: {}, query: {}, crawl_type: {}, number: {}, caption: {}, authentication: {}"
              .format(dir_prefix, query, crawl_type, number, caption, authentication))

        if crawl_type == "photos":
            # Browse target page
            self.browse_target_page(query)
            # Scroll down until target number photos is reached
            self.scroll_to_num_of_posts(number)
            # Scrape photo links
            self.scrape_photo_links(number, is_hashtag=query.startswith("#"))
            # Scrape captions if specified
            if caption is True:
                self.click_and_scrape_captions(number)

        elif crawl_type in ["followers", "following"]:
            # Need to login first before crawling followers/following
            print("You will need to login to crawl {}".format(crawl_type))
            self.login(authentication)

            # Then browse target page
            assert not query.startswith(
                '#'), "Hashtag does not have followers/following!"
            self.browse_target_page(query)
            # Scrape captions
            self.scrape_followers_or_following(crawl_type, query, number)
        else:
            print("Unknown crawl type: {}".format(crawl_type))
            self.quit()
            return
        # Save to directory
        print("Saving...")
        self.download_and_save(dir_prefix, query, crawl_type)

        # Quit driver
        print("Quitting driver...")
        self.quit()

    def browse_target_page(self, query):
        # Browse Hashtags
        if '#' in  query:
        #if query.startswith('\'\\''#'):
            #relative_url = urljoin('explore/tags/', query.strip('#'))
            relative_url = ''.join(['explore/tags/',query.strip('#')])
        else:  # Browse user page
            relative_url = query

        target_url = urljoin(HOST, relative_url)

        self._driver.get(target_url)
        return self

    def scroll_to_num_of_posts(self, number):
        # Get total number of posts of page
        #num_of_posts = re.search(r'"_fd86t"\>(\,?\d+\,?\d+)',
        #                     self._driver.page_source).group(1)

        try:
            _num_of_posts = WebDriverWait(self._driver, 100).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//span[contains(@class, '_fd86t')]")))
        except TimeoutException:
            print("Show total count detail {}".format(number))

        num_of_posts = _num_of_posts.text
        num_of_posts = int(num_of_posts.replace(',',''))

        print("posts: {}, number: {}".format(num_of_posts, number))
        number = number if number < num_of_posts else num_of_posts

        #element = self._driver.find_element_by_css_selector("._1cr2e")
        #self._driver.execute_script("arguments[0].click();", element)

        num_to_scroll = int((number - 12) / 12) + 1
        for _ in range(num_to_scroll):
            self._driver.execute_script(SCROLL_DOWN)
            time.sleep(0.5)
            #self.scrape_photo_links(300)
            #self._driver.execute_script(SCROLL_UP)
            #time.sleep(0.5)
            #self._driver.execute_script(SCROLL_DOWN)
            #time.sleep(0.5)
        return self

    def scrape_photo_links(self, number, is_hashtag=False):
        print("Scraping photo links...")
        #Image save regulation expression
        encased_photo_links = re.finditer(r'src="([https]+:...[\/\w \.-]*..[\/\w \.-]*'
                                          r'..[\/\w \.-]*..[\/\w \.-].jpg)', self._driver.page_source)
        #encased_photo_links = re.finditer(r'src="([https]+:...[\/\w \.-]*..[\/\w \.-]*'
        #                                  r'..[\/\w \.-]*..[\/\w \.-].jpg)', self._driver.page_source)


        soup = BeautifulSoup(self._driver.page_source, 'html.parser')
        _pl = soup.find_all('img')
        photo_links = [m.group(1) for m in encased_photo_links]

        print("Number of photo_links: {}".format(len(photo_links)))

        #begin = 0 if is_hashtag else 1

        self.data['photo_links'].extend(photo_links)
        self.data['photo_links']= list(set(self.data['photo_links']))
        #self.data['photo_links'] = photo_links
        return self

    def wait_element_xpath(self, elements_path):
        _f_post = ""
        try:
            WebDriverWait(self._driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, elements_path)
                )
            )
            _f_post = self._driver.find_element_by_xpath(elements_path)


        except TimeoutException:
            print("Exception for Show wait_element Xpath {}".format(elements_path))


        return _f_post

    def wait_element_xpath_either(self, elements_path1,elements_path2 ):
        _f_post = ""
        try:
            WebDriverWait(self._driver, 1).until(
                EC.presence_of_element_located(
                    (By.XPATH, elements_path1)
                )
            )
            _f_post = self._driver.find_element_by_xpath(elements_path1).get_attribute('src')


        except Exception:
            print("Exception for wait_element_xpath_either {}".format("first exception"))
            try:
                print("Exception for Show wait_element Xpath {}".format(elements_path2))
                _f_post = self._driver.find_element_by_xpath(elements_path2).get_attribute('src')
            except Exception:
                print("Exception for wait_element_xpath_either {}".format("second exception"))
                try:
                    _f_post = self._driver.find_element_by_xpath("//div[contains(@class, '_sxolz')]/div/div/div/div/img").get_attribute('src')
                except Exception:
                    print("Exception for wait_element_xpath_either {}".format("thitrd exception"))
                    _f_post = self._driver.find_element_by_xpath(
                        "//div[contains(@class, '_sxolz')]/div/div/div/img").get_attribute('src')


        return _f_post

    def wait_element_css_selector(self, elements_path):
        _f_post = ""
        try:
            _f_post = WebDriverWait(self._driver, 100).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, elements_path)
                )
            )
        except TimeoutException:
            _f_post = WebDriverWait(self._driver, 100).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, elements_path)
                )
            )
            print("Exception for Show wait_element Css Selector  {}".format(elements_path))
        return _f_post

    def get_element_tag_name(self, elements_tag):
        _f_post = ""
        try:
            WebDriverWait(self._driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, elements_tag))
            )
            _f_post = self._driver.find_element_by_tag_name(elements_tag)#.get_attribute('datetime')
            #m_time = datetime.datetime.strptime(_m_time, "%Y-%m-%dT%H:%M:%S.000Z")

        except NoSuchElementException:  # Forbidden
            print("Caption not found in the {} ids".format(elements_tag))
            #m_time = ""
        return _f_post


    def click_and_scrape_captions(self, number):
        print("Scraping captions...")
        captions = []
        ids = []
        modify_time = []
        id_mtime_col = {}
        id_mtime_row = []

        for post_num in range(number):
            sys.stdout.write("\033[F")
            print("Scraping captions {} / {}".format(post_num+1,number))
            if post_num == 0:  # Click on the first post
                wait_first_post = self.wait_element_xpath("//div[contains(@class, '_mck9w')]")
                time.sleep(1)
                wait_first_post_for_click = self.wait_element_xpath("//div[contains(@class, '_mck9w')]")
                wait_first_post_for_click.click()

                if number != 1:  #
                    init_right_arrow = self.wait_element_css_selector(CSS_RIGHT_ARROW)
                    init_right_arrow.click()


            elif number != 1:  # Click Right Arrow to move to next post
                right_arrow = self.wait_element_css_selector(CSS_RIGHT_ARROW)
                right_arrow.click()

            #Main Page를 들어가기위해 links를 가져온다
            #/html/body/div[3]/div/div[2]/div/article/header/div[2]/div[1]/div[1]/a
            #body > div: nth - child(
            #    13) > div > div._o0j5z > div > article > header > div._j56ec > div._74oom > div._eeohz > a
            #"//a[contains(@class, '_74oom _eeohz')]"
            _id_click1 = "'//a[contains(@class, '_pg23k _gvoze')]'"
            _id_click2 = "//a[contains(@class, '_2g7d5')]"
            wait_get_detail_id = self.wait_element_xpath(_id_click2)
            wait_get_detail_id.click()

            #ID를 가져 오기
            _id_detail_main = self.wait_element_xpath("//h1[contains(@class, '_rf3jb')]")
            id_detail_main = _id_detail_main.text
            print("id : {0}".format(id_detail_main))
            #POST 갯수를 가져오기

            _get_post_xpath = "//span[contains(@class, '_fd86t')]"
            _id_detail_count = self.wait_element_xpath(_get_post_xpath).text
            id_detail_count = int(_id_detail_count.replace(',',''))
            print("detail post count : {0}".format(id_detail_count))



            # First Post를 가져 오기
            f_post_detail = self.wait_element_xpath("//div[contains(@class, '_mck9w')]")
            f_post_detail.click()

            _m_time_elememt = self.get_element_tag_name("time")
            _m_time = _m_time_elememt.get_attribute('datetime')
            try:
                m_time =  datetime.datetime.strptime(_m_time, "%Y-%m-%dT%H:%M:%S.000Z")
            except Exception:
                print("Detail First Pos Modifu Time Error {} ")
                m_time = ""
            time.sleep(1)
            self._driver.execute_script("window.history.go(-2)")


            init_right_arrow = self.wait_element_css_selector(CSS_RIGHT_ARROW)
            init_right_arrow.click()

            id_mtime_row.append([id_detail_main, m_time,'Y',m_time,id_detail_count])
            #ids.append("1")

        self.data['captions'] = ids
        print(id_mtime_row)
        self.current_df = pd.DataFrame(id_mtime_row, columns=MASTER_DATA_COLUMN_LIST)
        #self.make_pandas(df)
        #df.to_csv("Main_crawling.csv")
        return self

    def click_and_1080_images(self, number):
        print("Scraping captions...")
        captions = []
        ids = []
        modify_time = []
        id_mtime_col = {}
        id_mtime_row = []

        for post_num in range(number):
            sys.stdout.write("\033[F")
            print("Scraping captions {} / {}".format(post_num+1,number))
            if post_num == 0:  # Click on the first post
                wait_first_post = self.wait_element_xpath("//div[contains(@class, '_mck9w')]")
                time.sleep(1)
                wait_first_post_for_click = self.wait_element_xpath("//div[contains(@class, '_mck9w')]")
                wait_first_post_for_click.click()

                if number != 1:  #
                    init_right_arrow = self.wait_element_css_selector(CSS_RIGHT_ARROW)
                    init_right_arrow.click()


            elif number != 1:  # Click Right Arrow to move to next post
                right_arrow = self.wait_element_css_selector(CSS_RIGHT_ARROW)
                right_arrow.click()

            #Main Page를 들어가기위해 links를 가져온다
            #/html/body/div[3]/div/div[2]/div/article/header/div[2]/div[1]/div[1]/a
            #body > div: nth - child(
            #    13) > div > div._o0j5z > div > article > header > div._j56ec > div._74oom > div._eeohz > a
            #"//a[contains(@class, '_74oom _eeohz')]"
            #_id_click1 = "'//a[contains(@class, '_pg23k _gvoze')]'"
            #_id_click2 = "//a[contains(@class, '_2g7d5')]"
            #wait_get_detail_id = self.wait_element_xpath(_id_click2)
            #wait_get_detail_id.click()

            soup = BeautifulSoup(self._driver.page_source, 'html.parser')
            _pl = soup.find_all('img')

            #ID를 가져 오기
            _id_detail_main = self.wait_element_xpath("//h1[contains(@class, '_rf3jb')]")
            id_detail_main = _id_detail_main.text
            print("id : {0}".format(id_detail_main))

            img_path = self.wait_element_xpath_either("//div[contains(@class, '_sxolz')]/div/div/div/div/div/div/img","//div[contains(@class, '_sxolz')]/div/div/div/div/div/img")
            #POST 갯수를 가져오기
            self.data['photo_links'].append(img_path)

            self.data['photo_links'] = list(set(self.data['photo_links']))

            #_get_post_xpath = "//span[contains(@class, '_fd86t')]"
            #_id_detail_count = self.wait_element_xpath(_get_post_xpath).text
            #id_detail_count = int(_id_detail_count.replace(',',''))
            #print("detail post count : {0}".format(id_detail_count))



            # First Post를 가져 오기
            #f_post_detail = self.wait_element_xpath("//div[contains(@class, '_mck9w')]")
            #f_post_detail.click()

            #_m_time_elememt = self.get_element_tag_name("time")
            #_m_time = _m_time_elememt.get_attribute('datetime')
            #try:
                #m_time =  datetime.datetime.strptime(_m_time, "%Y-%m-%dT%H:%M:%S.000Z")
            #except Exception:
                #print("Detail First Pos Modifu Time Error {} ")
                #m_time = ""
            #time.sleep(1)
            #self._driver.execute_script("window.history.go(-2)")


            init_right_arrow = self.wait_element_css_selector(CSS_RIGHT_ARROW)
            init_right_arrow.click()

            #id_mtime_row.append([id_detail_main, m_time,'Y',m_time,id_detail_count])
            #ids.append("1")

        self.data['captions'] = ids
        print(id_mtime_row)
        self.current_df = pd.DataFrame(id_mtime_row, columns=MASTER_DATA_COLUMN_LIST)
        #self.make_pandas(df)
        #df.to_csv("Main_crawling.csv")
        return self

    def make_pandas(self):
        pd_utils = pandas_utils()
        # At the first time
        #[x for x in os.listdir() if x.endswith(".txt")]
        if not os.path.exists(MASTER_DATA_PATH):
            os.mkdir(MASTER_DATA_PATH)

        filelists = [ _f for _f in os.listdir(MASTER_DATA_PATH) if _f in MASTER_DATA_FILE]
        if len(filelists) == 0:
            self.current_df.to_csv(''.join([MASTER_DATA_PATH , "/" , MASTER_DATA_FILE]))
        else:
            original_df = pd.read_csv(''.join([MASTER_DATA_PATH , "/" , MASTER_DATA_FILE]))
            columns_name = ['seq', 'id', 'm_time_ori', 'm_time_cur']
            result_temp = pd_utils.merge(original_df,self.current_df )
            result = result_temp[MASTER_DATA_COLUMN_LIST]
            #make backup file
            self.make_backup_file()
            #save csv file
            result = result.drop_duplicates()
            result.to_csv(''.join([MASTER_DATA_PATH, "/", MASTER_DATA_FILE]))

        return self
    def make_backup_file(self):
        #폴더체크
        backup_file_name = "bk_"+ datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ".csv"

        if not os.path.exists(MASTER_DATA_BACKUP):
            os.mkdir(MASTER_DATA_BACKUP)

        shutil.copy2(''.join([MASTER_DATA_PATH , "/" , MASTER_DATA_FILE]), ''.join([MASTER_DATA_BACKUP,"/",backup_file_name]))  # complete target filename given


    def scrape_followers_or_following(self, crawl_type, query, number):
        print("Scraping {}...".format(crawl_type))
        if crawl_type == "followers":
            FOLLOW_ELE = CSS_FOLLOWERS
            FOLLOW_PATH = FOLLOWER_PATH
        elif crawl_type == "following":
            FOLLOW_ELE = CSS_FOLLOWING
            FOLLOW_PATH = FOLLOWING_PATH

        # Locate follow list
        follow_ele = WebDriverWait(self._driver, 5).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, FOLLOW_ELE.format(query)))
        )

        # when no number defined, check the total items
        if number is 0:
            number = int(filter(str.isdigit, str(follow_ele.text)))
            print("getting all " + str(number) + " items")

        # open desired list
        follow_ele.click()

        title_ele = WebDriverWait(self._driver, 5).until(
            EC.presence_of_element_located(
                (By.XPATH, FOLLOW_PATH))
        )
        List = title_ele.find_element_by_xpath(
            '..').find_element_by_tag_name('ul')
        List.click()

        # Loop through list till target number is reached
        num_of_shown_follow = len(List.find_elements_by_xpath('*'))
        while len(List.find_elements_by_xpath('*')) < number:
            element = List.find_elements_by_xpath('*')[-1]
            # Work around for now => should use selenium's Expected Conditions!
            try:
                element.send_keys(Keys.PAGE_DOWN)
            except Exception as e:
                time.sleep(0.1)

        follow_items = []
        for ele in List.find_elements_by_xpath('*')[:number]:
            follow_items.append(ele.text.split('\n')[0])

        self.data[crawl_type] = follow_items

    def detect_face_from_image(self, pnet, rnet, onet, raw_filepath, filename,detect_dir_path):
        _detecter = face_detect_crawling()
        #filename = raw_filepath

        image = cv2.imread(raw_filepath, flags=cv2.IMREAD_COLOR)
        #config = tf.ConfigProto(device_count={'GPU': 0})
        #with tf.Session(config=config) as sess:
        #pnet, rnet, onet = detect_face.create_mtcnn(sess, None)
            # frame, self.minsize, self.pnet, self.rnet, self.onet,self.threshold, self.factor
        minsize = 20
        threshold = [0.6, 0.7, 0.7]
        factor = 0.709
        margin = 90
            # image_size = 300
            # cropped_size = 30  # rotation use
        detect_type = 'mtcnn'  # dlib, mtcnn, hog, cnn
        #rotation = False
        aligned, boxes = face_detect_crawling.get_boxes_frame(minsize, pnet, rnet, onet, threshold, factor, image,
                                                                  detect_type, margin)
        detect_filepath =  os.path.join(detect_dir_path, filename)
        if aligned != None:
            #cv2.imshow("Window", aligned);
            #print("detect face from images {0}".format(detect_filepath))
            cv2.imwrite(detect_filepath,aligned)
        else:
            print("No detect face from images {0}".format(detect_filepath))
        #print("success")

    def insight_detect_face_from_image(self ):
        _detecter = face_detect_crawling()
        #filename = raw_filepath
        raw_filepath = '/home/dev/insta_crawling/data/korea_486/raw/1_20180222093838.jpg'
        image = cv2.imread(raw_filepath, flags=cv2.IMREAD_COLOR)


        #config = tf.ConfigProto(device_count={'GPU': 0})
        #with tf.Session(config=config) as sess:
        #pnet, rnet, onet = detect_face.create_mtcnn(sess, None)
            # frame, self.minsize, self.pnet, self.rnet, self.onet,self.threshold, self.factor
        # minsize = 20
        # threshold = [0.6, 0.7, 0.7]
        # factor = 0.709
        # margin = 90
        #     # image_size = 300
        #     # cropped_size = 30  # rotation use
        # detect_type = 'mtcnn'  # dlib, mtcnn, hog, cnn
        # #rotation = False
        # aligned, boxes = face_detect_crawling.get_boxes_frame(minsize, pnet, rnet, onet, threshold, factor, image,
        #                                                           detect_type, margin)
        # detect_filepath =  os.path.join(detect_dir_path, filename)
        # if aligned != None:
        #     #cv2.imshow("Window", aligned);
        #     #print("detect face from images {0}".format(detect_filepath))
        #     cv2.imwrite(detect_filepath,aligned)
        # else:
        #     print("No detect face from images {0}".format(detect_filepath))
        # #print("success")
        print('Loading feature extraction model')
        #self.feature_model_dir = 'model-r50-am-lfw' #'model-r34-amf'
        #self.feature_model = self.pre_model_dir + self.feature_model_dir + '/' + 'model,0'
        self.feature_model = '/home/dev/insta_crawling/align/models'+ '/' + 'model,0'
        self.threshold = 1.24
        self.image_size = '112,112'
        self.model = self.feature_model

        mtcnn_model = face_embedding.FaceModel(self)

        #self.logger = logging.getLogger('myapp')
        #hdlr = logging.FileHandler(self.log_dir + '/myface.log')
        #formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        #hdlr.setFormatter(formatter)
        #self.logger.addHandler(hdlr)
        #self.logger.setLevel(logging.WARNING)

        #if self.detect_type == 'mtcnn_caffe':
        bbox, points = mtcnn_model.get_boxes(image)
        boxes = [bbox]
        box_color = (120, 160, 230)

        draw_circle_flag = True
        cv2.rectangle(image, (int(boxes[0][0]), int(boxes[0][1])), (int(boxes[0][2]), int(boxes[0][3])), box_color,
                      1)
        # # Point 눈위치
        # if draw_circle_flag:
        #     for i in range(5):
        #         cv2.circle(image, (points[0][i], points[0][i + 5]), 1, (0, 0, 255), 2)
        cv2.circle(image, (points[0][0], points[0][5]), 1, (0, 0, 255), 2) #왼쪽눈
        cv2.circle(image, (points[0][1], points[0][6]), 1, (0, 0, 255), 2) #오른쪽 눈

        #각도 구하기
        dx = points[0][1] - points[0][0]
        dy = points[0][6] - points[0][5]
        nouse = (points[0][2] , points[0][7])
        #double
        rad = math.atan2(dy, dx);

        degree = (rad * 180.0) / math.pi;

        rotate = cv2.getRotationMatrix2D(nouse, degree, 1)  # 1? ??/??????.
        r_images = cv2.warpAffine(image, rotate, (700,400))


        #눈 그리고, 선 긋고, 수직선 긋고, 각도 재고, 돌리고, 눈을 특정 포인트로 이동하고, 잘라내고

        #400, 700

        #한번 더 태운다
        bbox2, points2 = mtcnn_model.get_boxes(r_images)
        boxes2 = [bbox]
        box_color2 = (120-100, 160, 0)

        cv2.rectangle(r_images, (int(boxes2[0][0]), int(boxes2[0][1])), (int(boxes2[0][2]), int(boxes2[0][3])), box_color2,
                      1)
        #         cv2.circle(image, (points[0][i], points[0][i + 5]), 1, (0, 0, 255), 2)
        cv2.circle(r_images, (points2[0][0], points2[0][5]), 1, (0, 255, 0), 2) #왼쪽눈
        cv2.circle(r_images, (points2[0][1], points2[0][6]), 1, (0, 255, 0), 2) #오른쪽 눈
        cv2.circle(r_images, (points2[0][2], points2[0][7]), 1, (0, 255, 0), 2)  # 오른쪽 눈

        cv2.imshow('img', r_images)

        #warp = face_preprocess.preprocess(raw_filepath, bbox=boxes, landmark=points)
        #preprocess
        print('각도는??? {0}'.format(degree))

    def download_and_save(self, dir_prefix, query, crawl_type,id, pnet, rnet, onet):
        # Check if is hashtag
        dir_name = query.lstrip(
            '#') + '.hashtag' if query.startswith('#') else query

        raw_dir_path = os.path.join(dir_prefix , dir_name,'raw')
        detect_dir_path = os.path.join(dir_prefix, dir_name,'detect')

        if not os.path.exists(raw_dir_path):
            os.makedirs(raw_dir_path)
        if not os.path.exists(detect_dir_path):
            os.makedirs(detect_dir_path)

        print("Saving to directory: {}".format(raw_dir_path))

        # Save Photos
        for idx, photo_link in enumerate(self.data['photo_links'], 0):
            sys.stdout.write("\033[F")
            print("Downloading {} images to ".format(idx + 1))
            # Filename
            _, ext = os.path.splitext(photo_link)
            #Filename _make
            #seq + date +
            _file_list_recent = os.listdir(raw_dir_path)
            #_file_list_sort = _file_list_recent.sort()


            _file_list_end = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            if _file_list_recent is None  or _file_list_recent.__len__() == 0:
                _idx = 1
            else:
                #get max file number in the directory
                exist_filename = sorted([int(_x.split('_')[0]) for _x in _file_list_recent], reverse=True)[0]
                _idx = int(exist_filename)+ 1

            #raw file save
            filename = str(_idx) + '_' +_file_list_end+ ext
            raw_filepath = os.path.join(raw_dir_path, filename)
            # Send image request
            urlretrieve(photo_link, raw_filepath)
            #face detection file save
            #face_detect_dir_path = os.path.join(dir_prefix, 'face_detect', dir_name)
             #image filename
            self.detect_face_from_image(pnet, rnet, onet, raw_filepath, filename,detect_dir_path)


        # Save Captions
        for idx, caption in enumerate(self.data['captions'], 0):

            filename = str(idx) + '.txt'
            filepath = os.path.join(raw_dir_path, filename)

            with codecs.open(filepath, 'w', encoding='utf-8') as fout:
                fout.write(caption + '\n')

        # Save followers/following
        filename = crawl_type + '.txt'
        filepath = os.path.join(raw_dir_path, filename)
        if len(self.data[crawl_type]):
            with codecs.open(filepath, 'w', encoding='utf-8') as fout:
                for fol in self.data[crawl_type]:
                    fout.write(fol + '\n')
        return self



    def save_after_crawling_master_data(self,id):
        read_df = pd.read_csv(''.join([MASTER_DATA_PATH, "/", MASTER_DATA_FILE]))
        #read_df.loc[read_df['id'] == id]['ActiveFlag'] = 'N'
        read_df.loc[read_df['id'] == id, 'ActiveFlag'] = 'N'
        read_df.loc[read_df['id'] == id, 'Crawling_time'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        read_df.loc[read_df['id'] == id, 'ModifyDatetime'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result = read_df[MASTER_DATA_COLUMN_LIST]
        result.to_csv(''.join([MASTER_DATA_PATH, "/", MASTER_DATA_FILE]))
        return self


def load_master_data():
    try:
        original_df = pd.read_csv(''.join([MASTER_DATA_PATH, "/", MASTER_DATA_FILE])).drop_duplicates()
        except_df = pd.read_csv(''.join([EXCEPT_DATA_PATH, "/", EXCEPT_DATA_FILE]))

        #EXCEPT_DATA_PATH = './except_data'
        #EXCEPT_DATA_FILE = 'crowling_except_data.csv'

        minium_post_num = 300
        pd_utils = pandas_utils(300)

        active_flag_modify = pd_utils.change_activeflag_by_total_posts(original_df,minium_post_num)
        active_flag_modify = active_flag_modify[MASTER_DATA_COLUMN_LIST]
        active_flag_modify.to_csv(''.join([MASTER_DATA_PATH, "/", MASTER_DATA_FILE]))

        get_activeflag_start_insta_id = original_df.loc[original_df['ActiveFlag'] == 'Y']
        #get_substract_except_insta_id = get_activeflag_start_insta_id.loc[original_df['id'] != except_df['id']]
        get_substract_except_insta_id = get_activeflag_start_insta_id[~get_activeflag_start_insta_id['id'].isin(except_df['id'].values.tolist())]
        result = get_total_post_start_insta_id = get_substract_except_insta_id.loc[get_substract_except_insta_id['Total_post'].astype('int') > 300]['id']

        #get_start_insta_id = _get_start_insta_id.dro
        print("Downloading instafram images by id count : {0}".format(get_total_post_start_insta_id.__len__()))
        #return result
    except Exception:
        print("Master Data Load Failed ")
        result = pd.Series([])
    return result

def main():
    #   Arguments  #
    parser = argparse.ArgumentParser(description='Instagram Crawler')
    parser.add_argument('-d', '--dir_prefix', type=str,
                        default='./data/', help='directory to save results')
    parser.add_argument('-q', '--query', type=str, default='jiweon501',
                        help="target to crawl, add '#' for hashtags")
    parser.add_argument('-t', '--crawl_type', type=str,
                        default='photos', help="Options: 'photos' | 'followers' | 'following'")
    parser.add_argument('-n', '--number', type=int, default=0,
                        help='Number of posts to download: integer')
    parser.add_argument('-c', '--caption', action='store_true', default=True,
                        help='Add this flag to download caption when downloading photos')
    parser.add_argument('-l', '--headless', default=False, action='store_true',
                        help='If set, will use PhantomJS driver to run script as headless')
    parser.add_argument('-a', '--authentication', type=str, default=None,
                        help='path to authentication json file')
    parser.add_argument('-f', '--firefox_path', type=str, default=None,
                        help='path to Firefox installation')

    parser.add_argument('-nd', '--number_detail', type=int, default=0,
                        help='Number of detail posts to download: integer')

    args = parser.parse_args()
    #
    # config = tf.ConfigProto(device_count={'GPU': 0})
    # sess =  tf.Session(config=config)
    # pnet, rnet, onet = detect_face.create_mtcnn(sess, None)
        # frame, self.minsize, self.pnet, self.rnet, self.onet,self.threshold, self.factor

    #  End Argparse #
    #init arg
    crawler = InstagramCrawler(headless=args.headless, firefox_path=args.firefox_path, firefox=False)
    # crawler.crawl(dir_prefix=args.dir_prefix,
    #               query=args.query,
    #               crawl_type=args.crawl_type,
    #               number=args.number,
    #               caption=args.caption,
    #               authentication=args.authentication)

    # # # # get Total id by Tag
    # crawler.browse_target_page(args.query) \
    #        .scroll_to_num_of_posts(args.number) \
    #        .click_and_scrape_captions(args.number) \
    #        .make_pandas()

#.scrape_photo_links(args.number) \

    # for _id  in load_master_data():
    #     print('Detail save picture : {0}'.format(_id))
    #     crawler.browse_target_page(_id) \
    #            .scroll_to_num_of_posts(args.number_detail) \
    #            .click_and_1080_images(args.number_detail) \
    #            .download_and_save(args.dir_prefix,_id,args.dir_prefix,_id, pnet, rnet, onet) \
    #            .save_after_crawling_master_data(_id)
    # # .scrape_photo_links(args.number_detail) \
    # sess.close()
    crawler.insight_detect_face_from_image()

if __name__ == "__main__":
    main()
