from __future__ import division

import argparse
import codecs
from collections import defaultdict
import json
import os
import re
import sys
import time
try:
    from urlparse import urljoin
    from urllib import urlretrieve
except ImportError:
    from urllib.parse import urljoin
    from urllib.request import urlretrieve

import datetime

import requests
import selenium
from selenium import webdriver
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# HOST
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
            #self._driver = webdriver.PhantomJS()
            #self._driver = webdriver.PhantomJS('/home/hyunsh/insta_crawling/phantomjs-2.1.3/phantomjs')
            options = webdriver.ChromeOptions()
            options.add_argument('headless')
            options.add_argument('window-size=1920x1080')
            options.add_argument("disable-gpu")

            # binary = FirefoxBinary(firefox_path)
            self._driver = webdriver.Chrome('/home/hyunsh/insta_crawling/chrome/chromedriver', chrome_options=options)
        else:
            if firefox :
            # credit to https://github.com/SeleniumHQ/selenium/issues/3884#issuecomment-296990844
                binary = FirefoxBinary(firefox_path)
                self._driver = webdriver.Firefox(firefox_binary=binary)
            else:
                #binary = FirefoxBinary(firefox_path)
                self._driver = webdriver.Chrome('/home/hyunsh/insta_crawling/chrome/chromedriver')

        #self._driver.implicitly_wait(10)
        self.data = defaultdict(list)

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
            relative_url = 'explore/tags/대한민국'
        else:  # Browse user page
            relative_url = query

        #target_url = urljoin(HOST, relative_url)
        #target_url = "http://www.instagram.com/instagram/"

        #target_url = "https://www.instagram.com/jiweon501/"
        target_url = urljoin(HOST, relative_url)

        self._driver.get(target_url)

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

        # num_of_posts = re.search(r'"_fd86t.{0,7}"\>(\,?\d+\,?\d+)',
        #                      self._driver.page_source).group(1)
        #num_info = re.search(r'\], "count": \d+',
        #                     self._driver.page_source).group()
        num_of_posts = int(num_of_posts.replace(',',''))
        #num_of_posts = int(re.findall(r'\d+', num_info)[0])
        print("posts: {}, number: {}".format(num_of_posts, number))
        number = number if number < num_of_posts else num_of_posts

        #another way
        #element = self._driver.find_element_by_class_name('_1cr2e._epyes')
        element = self._driver.find_element_by_css_selector("._1cr2e")
        self._driver.execute_script("arguments[0].click();", element)

        # scroll page until reached
        # loadmore = WebDriverWait(self._driver, 10).until(
        #     EC.presence_of_element_located(
        #         (By.CSS_SELECTOR, CSS_LOAD_MORE))
        # )
        # loadmore.click()

        num_to_scroll = int((number - 12) / 12) + 1
        for _ in range(num_to_scroll):
            self._driver.execute_script(SCROLL_DOWN)
            time.sleep(0.5)
            self._driver.execute_script(SCROLL_UP)
            time.sleep(0.5)

    def scrape_photo_links(self, number, is_hashtag=False):
        print("Scraping photo links...")
        encased_photo_links = re.finditer(r'src="([https]+:...[\/\w \.-]*..[\/\w \.-]*'
                                          r'..[\/\w \.-]*..[\/\w \.-].jpg)', self._driver.page_source)

        photo_links = [m.group(1) for m in encased_photo_links]

        print("Number of photo_links: {}".format(len(photo_links)))

        begin = 0 if is_hashtag else 1

        self.data['photo_links'] = photo_links[begin:number + begin]

    def click_and_scrape_captions(self, number):
        print("Scraping captions...")
        captions = []
        ids = []
        modify_time = []

        for post_num in range(number):
            sys.stdout.write("\033[F")
            print("Scraping captions {} / {}".format(post_num+1,number))
            if post_num == 0:  # Click on the first post
                # should wait for loading
                # another way
                #next_element = self._driver.find_element_by_class_name('_mck9w')
                #self._driver.execute_script("arguments[0].click();", next_element)
                _f_post = None
                try:
                    WebDriverWait(self._driver, 100).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, CSS_DETAIL_POPUP)))
                except TimeoutException:
                    print("Show detail {}".format(post_num))
                    break

                try:
                    WebDriverWait(self._driver, 100).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "div._70iju:nth-child(1) > div:nth-child(1)")
                        )
                    )
                except TimeoutException:
                    print("Show detail2 {}".format(post_num))
                    break

                try:
                    _f_post = WebDriverWait(self._driver, 100).until(
                        EC.presence_of_element_located(
                            (By.XPATH, "//div[contains(@class, '_mck9w')]")
                        )
                    )
                except TimeoutException:
                    print("Show detail2 {}".format(post_num))
                    break

                #
                time.sleep(1)
                _f_post2 = self._driver.find_element_by_xpath(
                    FIREFOX_FIRST_POST_PATH)
                _f_post2.click()

                # _f_post3 = self._driver.find_element_by_xpath(FIREFOX_FIRST_POST_PATH)
                # self._driver.execute_script("arguments[0].click();", _f_post3)


                #popup = self._driver.find_element_by_css_selector(
                #    "div._70iju:nth-child(1) > div:nth-child(1)").click()
                #popup2 = self._driver.find_element_by_xpath("//div[contains(@class, '_mck9w')]").find_element_by_tag_name("a").click()
                #_f_post.find_element_by_tag_name("a").click()

                if number != 1:  #
                    # WebDriverWait(self._driver, 100).until(
                    #     EC.presence_of_element_located(
                    #         (By.CSS_SELECTOR, "._3a693")
                    #     )
                    # )
                    try:
                        init_right_arrow = WebDriverWait(self._driver, 1).until(
                            EC.presence_of_element_located(
                                (By.CSS_SELECTOR, CSS_RIGHT_ARROW)
                            )
                        )
                    except:
                        init_right_arrow = WebDriverWait(self._driver, 1).until(
                            EC.presence_of_element_located(
                                (By.CSS_SELECTOR, CSS_RIGHT_ARROW)
                            )
                        )

                        # popup = self._driver.find_element_by_css_selector(
                        #     "div._70iju:nth-child(1) > div:nth-child(1)").click()
                        #
                    init_right_arrow.click()


            elif number != 1:  # Click Right Arrow to move to next post
                url_before = self._driver.current_url

                right_arrow = WebDriverWait(self._driver, 100).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, CSS_RIGHT_ARROW)
                    )
                )
                right_arrow.click()

                #
                # self._driver.find_element_by_css_selector(
                #     CSS_RIGHT_ARROW).click()

                # Wait until the page has loaded

                # try:
                #     WebDriverWait(self._driver, 20).until(
                #         url_change(url_before))
                # except TimeoutException:
                #     print("Time out in caption scraping at number {}".format(post_num))
                #     break

            # Parse caption
            try:
                time_element = WebDriverWait(self._driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "time"))
                )
                caption = time_element.find_element_by_xpath(
                    TIME_TO_CAPTION_PATH).text
            except NoSuchElementException:  # Forbidden
                print("Caption not found in the {} photo".format(post_num))
                caption = ""

            captions.append(caption)

            try:
                _ids_element = WebDriverWait(self._driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//div[contains(@class, '_eeohz')]"))
                )
                id = _ids_element.find_element_by_xpath(
                    "//div[contains(@class, '_eeohz')]").text


            except NoSuchElementException:  # Forbidden
                print("Caption not found in the {} ids".format(post_num))
                id = ""
            ids.append(id)

            try:
                WebDriverWait(self._driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "time"))
                )
                _m_time = self._driver.find_element_by_tag_name('time').get_attribute('datetime')
                m_time = datetime.datetime.strptime(_m_time,"%Y-%m-%dT%H:%M:%S.000Z")

            except NoSuchElementException:  # Forbidden
                print("Caption not found in the {} ids".format(post_num))
                m_time = ""

            modify_time.append(m_time)




        self.data['captions'] = captions
        self.data['ids'] = ids
        self.data['modify_time'] = modify_time

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

    def download_and_save(self, dir_prefix, query, crawl_type):
        # Check if is hashtag
        dir_name = query.lstrip(
            '#') + '.hashtag' if query.startswith('#') else query

        dir_path = os.path.join(dir_prefix, dir_name)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

        print("Saving to directory: {}".format(dir_path))

        # Save Photos
        for idx, photo_link in enumerate(self.data['photo_links'], 0):
            sys.stdout.write("\033[F")
            print("Downloading {} images to ".format(idx + 1))
            # Filename
            _, ext = os.path.splitext(photo_link)
            filename = str(idx) + ext
            filepath = os.path.join(dir_path, filename)
            # Send image request
            urlretrieve(photo_link, filepath)

        # Save Captions
        for idx, caption in enumerate(self.data['captions'], 0):

            filename = str(idx) + '.txt'
            filepath = os.path.join(dir_path, filename)

            with codecs.open(filepath, 'w', encoding='utf-8') as fout:
                fout.write(caption + '\n')

        # Save followers/following
        filename = crawl_type + '.txt'
        filepath = os.path.join(dir_path, filename)
        if len(self.data[crawl_type]):
            with codecs.open(filepath, 'w', encoding='utf-8') as fout:
                for fol in self.data[crawl_type]:
                    fout.write(fol + '\n')


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
    args = parser.parse_args()

    #  End Argparse #
    #init arg
    crawler = InstagramCrawler(headless=args.headless, firefox_path=args.firefox_path, firefox=False)
    crawler.crawl(dir_prefix=args.dir_prefix,
                  query=args.query,
                  crawl_type=args.crawl_type,
                  number=args.number,
                  caption=args.caption,
                  authentication=args.authentication)


if __name__ == "__main__":
    main()
