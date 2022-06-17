import os
import time
import scrapy
import re
import pandas as pd
from pydispatch import dispatcher
from scrapy import signals
from scrapy.utils.project import get_project_settings
from urllib.parse import urljoin
from selenium.webdriver.common.keys import Keys
from urllib.parse import urlparse

from capture_instagram.browser_wrapper import BrowserWrapperMixin, SeleniumRequest


class CaptureSimpleSpider(scrapy.Spider, BrowserWrapperMixin):
    name = 'capture_simple'
    allowed_domains = ['instagram.com']

    def __init__(self, **kwargs):
        super().__init__(name=self.name, **kwargs)
        BrowserWrapperMixin.__init__(self)

        self.post_links = None
        self.post_index = 0

        self.user_links = []
        self.user_index = 0

        self.browser = self.connect_browser()

        self.enable_image(enable=False)

        # 设置信号量，当收到spider_closed信号时，调用mySpiderCloseHandle方法，关闭chrome
        dispatcher.connect(receiver=self.mySpiderCloseHandle,
                           signal=signals.spider_closed
                           )

    def mySpiderCloseHandle(self, spider):
        self.enable_image(enable=True)
        pass

    def error(self, spider):
        self.enable_image(enable=True)
        pass

    def get_tag_home_url(self):
        return f'https://www.instagram.com/explore/tags/{self.tag}/'

    def start_crawl_tag_home(self):
        # Read all link for filtering
        try:
            with open(self.output_file, encoding='utf8') as f:
                self.post_links = set(filter(lambda x: x, map(lambda x: x.strip(), f.read().split('\n'))))
        except Exception as e:
            self.post_links = set()

        try:
            return SeleniumRequest(
                url=self.get_tag_home_url(),
                wait_xpaths=['//button[text()="Follow"]'],
                callback=self.parse_tag_home_page,
                errback=self.error
            )
        except Exception as e:
            return None

    def save_post_link(self, links):
        links = list(set(links) - self.post_links)

        if len(links):
            with open(self.output_file, 'at+', encoding='utf8') as f:
                f.write('\n'.join(links)+'\n')

        # Add to saved link set
        self.post_links = self.post_links.union(set(links))
        return len(links)

    def parse_tag_home_page(self, response):
        """
        Get list of most recent post links
        """
        links = response.xpath('//h2[text()="Most recent"]/following-sibling::div[1]/div/div//a/attribute::href').getall()
        total_saved = self.save_post_link(links)
        while True:
            self.browser.find_element_by_tag_name('body').send_keys(Keys.END)
            time.sleep(0.5)
            response = self.get_response_from_browser(None)
            links = response.xpath('//h2[text()="Most recent"]/following-sibling::div[1]/div/div//a/attribute::href').getall()
            total_saved += self.save_post_link(links)

            self.crawler.stats.set_value('total_saved', total_saved)

            if len(self.post_links) >= int(self.max_count):
                break

    def get_post_detail_request(self, link):
        return SeleniumRequest(
            url=urljoin('https://www.instagram.com/', link),
            wait_xpaths=['//button/div[text()="Follow"]'],
            callback=self.parse_post_detail_page,
            meta={'post_link': link},
            errback=self.error
        )

    def start_crawl_post_detail(self):
        try:
            path = os.path.join(get_project_settings().get('DATA_DIR'), f'post_links_{self.tag_detail}.txt')
            with open(path, encoding='utf8') as f:
                post_links = list(filter(lambda x: x, map(lambda x: x.strip(), f.read().split('\n'))))

            try:
                output_path = list(self.settings.get('FEEDS').attributes.keys())[0]
                df = pd.read_csv(output_path)
                captured_links = set(df['post_link'])
            except Exception as e:
                captured_links = set()

            # Filter out captured links, keep the order
            self.post_links = [l for l in post_links if l not in captured_links]

            if self.post_links:
                self.post_index = 0
                return self.get_post_detail_request(self.post_links[self.post_index])
        except Exception as e:
            return None

    @staticmethod
    def is_post_english_only(post_text):
        for c in post_text:
            if ord(c) >= 128:
                return False
        return True

    def parse_post_detail_page(self, response):
        time.sleep(5)
        while True:
            # 通过不停点击列表下面的“+”按钮，加载所有评论
            try:
                more_comments_button = self.browser.find_element_by_xpath('//article/div[1]/div[2]/div[1]/div[2]/div[1]/ul/li/div/button')
                more_comments_button.click()
                time.sleep(5)
            except Exception as e:
                break
        response = self.get_response_from_browser(response.meta)

        user_name = response.xpath('//header//a/text()').get()
        user_link = response.xpath('//header//a/attribute::href').get()

        post_texts = response.xpath('//article/div/div[2]/div/div[2]/div[1]/ul/div//span//text()').getall()
        post_text = '\n'.join(post_texts[1:])  # First is the user name
        ats = response.xpath('//article/div/div[2]/div/div[2]/div[1]/ul/div//span//a[starts-with(text(), "@")]/text()').getall()
        ats_num = len(ats)
        hashes = response.xpath('//article/div/div[2]/div/div[2]/div[1]/ul/div//span//a[starts-with(text(), "#")]/text()').getall()
        hashes_num = len(hashes)

        # Remove @xx and #xx from post text
        # for i in [*ats, *hashes]:
        for i in [*ats]:
            post_text = post_text.replace(i, '')

        post_text = post_text.strip()

        post_len = len(post_text)

        question_count = len(re.findall(r'\?', post_text))

        comments_num = len(response.xpath('//article/div/div[2]/div/div[2]/div[1]/ul/ul'))

        # liked_path = urlparse(response.url).path + '/liked_by/'
        # liked_path = liked_path.replace('//', '/')  # Incase something wrong

        likes = response.xpath(f'//a[contains(@href, "/liked_by/")]//span/text()').get()
        if likes:
            likes_num = self.parse_number(likes)
        else:
            like_texts = set()
            try:
                # liked_path = urlparse(response.url).path + '/liked_by/'
                # liked_path = liked_path.replace('//', '/')  # Incase something wrong
                a = self.browser.find_element_by_xpath(f'//a[contains(@href, "/liked_by/")]')
                a.click()
                time.sleep(2)
                likes_dialog = self.browser.find_element_by_xpath('//div[@aria-label="Likes" and @role="dialog"]')
                
                # Display only 11 items each time
                while True:
                    likes = likes_dialog.find_elements_by_xpath('.//div[@aria-labelledby]')
                    texts = set([l.text for l in likes])
                    if len(like_texts) > 1000 or not texts - like_texts:
                        # Stop scroll if no more new likes
                        break
                    like_texts = like_texts.union(texts)
                    #     like_container = likes_dialog.find_element_by_xpath('./div[1]/div[3]/div[1]')
                    #     like_container.click()
                    # Because some account do not show name, we need to check on the middle 1/3 items to ensure click is working
                    for i in range(len(likes)//3, len(likes)*2//3):
                        try:
                            # This is the text below email link, so that click it will not cause jump off
                            div_name = likes[i].find_element_by_xpath('./div[2]/div[2]')
                            div_name.click()
                            time.sleep(0.1)
                        except Exception as e:
                            pass
                    time.sleep(0.1)
                    body = self.browser.find_element_by_css_selector('body')
                    body.send_keys(Keys.PAGE_DOWN)
                    time.sleep(0.3)
                likes_num = len(like_texts)
            except Exception as e:
                likes_num = len(like_texts)

        time_text = response.xpath('//article/div/div[2]/div/div[2]/div[2]//time/attribute::datetime').get()

        # Save only Englist
        # if self.is_post_english_only(post_text):
        yield {
            'name': user_name,
            'link': user_link,
            'post_link': response.meta['post_link'],
            'comments_num': comments_num,
            'likes_num': likes_num,
            'ats_num': ats_num,
            'hashes_num': hashes_num,
            'text_length': post_len,
            'datetime': time_text,
            'post_text': post_text,
            'question_count': question_count
        }

        if self.post_index < len(self.post_links) - 1:
            self.post_index += 1
            yield self.get_post_detail_request(self.post_links[self.post_index])

        time.sleep(1)

    def get_user_home_request(self, link):
        return SeleniumRequest(
            url=urljoin('https://www.instagram.com/', link),
            wait_xpaths=['//button/div[text()="Follow"]'],
            callback=self.parse_user_home_page,
            meta={'link': link},
            errback=self.error
        )

    def start_crawl_user_follower(self):
        try:
            path1 = os.path.join(get_project_settings().get('DATA_DIR'), f'posts_{self.user_follower}.csv')
            df1 = pd.read_csv(path1)

            try:
                # path2 = os.path.join(get_project_settings().get('DATA_DIR'), f'user_follower.csv')
                output_path = list(self.settings.get('FEEDS').attributes.keys())[0]
                df2 = pd.read_csv(output_path)
                captured_links = set(df2['link'])
            except Exception as e:
                captured_links = set()

            # Do not crawl links that are already captured
            self.user_links = [l for l in list(df1['link']) if l not in captured_links]
            self.user_index = 0
            if len(self.user_links) > 0:
                return self.get_user_home_request(self.user_links[self.user_index])
        except Exception as e:
            return None
    
    def parse_number(self, num_text):
        """
        There are multiple number format:
        1. 15
        2. 13,345
        3. 10.2k
        4. 5.5m
        """
        mult = 1
        num_text = num_text.replace(',', '').strip()
        if num_text.lower()[-1] == 'k':
            mult = 1000
            num_text = num_text[:-1]
        elif num_text.lower()[-1] == 'm':
            mult = 1000000
            num_text = num_text[:-1]

        return int(float(num_text) * mult)

    def parse_user_home_page(self, response):
        followers_text = response.xpath(f'//a[@href="{response.meta["link"]}followers/"]//span/text()').get()
        if followers_text:
            followers = self.parse_number(followers_text)
        else:
            followers = 0
            
        posts_text = response.xpath(f'//header/section/ul/li[1]/div/span/text()').get()
        if posts_text:
            posts = self.parse_number(posts_text)
        else:
            posts = 0

        following_text = response.xpath(f'//header/section/ul/li[3]//span/text()').get()
        if following_text:
            following = self.parse_number(following_text)
        else:
            following = 0

        yield {
            'link': response.meta['link'],
            'posts': posts,
            'followers': followers,
            'following': following
        }

        if self.user_index < len(self.user_links) - 1:
            self.user_index += 1
            yield self.get_user_home_request(self.user_links[self.user_index])

        time.sleep(1)

    def start_requests(self):
        request = self.start_crawl_tag_home()

        if not request:
            request = self.start_crawl_post_detail()

        if not request:
            request = self.start_crawl_user_follower()

        if request:
            yield request
