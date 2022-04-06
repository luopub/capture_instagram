import os
import time
import scrapy
import pandas as pd
from pydispatch import dispatcher
from scrapy import signals
from scrapy.utils.project import get_project_settings
from urllib.parse import urljoin
from selenium.webdriver.common.keys import Keys

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
        user_name = response.xpath('//header//a/text()').get()
        user_link = response.xpath('//header//a/attribute::href').get()

        post_texts = response.xpath('//article/div/div[2]/div/div[2]/div[1]/ul/div//span//text()').getall()
        post_text = '\n'.join(post_texts[1:])  # First is the user name
        ats = response.xpath('//article/div/div[2]/div/div[2]/div[1]/ul/div//span//a[starts-with(text(), "@")]/text()').getall()
        ats_num = len(ats)
        hashes = response.xpath('//article/div/div[2]/div/div[2]/div[1]/ul/div//span//a[starts-with(text(), "#")]/text()').getall()
        hashes_num = len(hashes)

        # Remove @xx and #xx from post text
        for i in [*ats, *hashes]:
            post_text = post_text.replace(i, '')

        post_text = post_text.strip()

        post_len = len(post_text)

        comments_num = len(response.xpath('//article/div/div[2]/div/div[2]/div[1]/ul/ul'))

        like_by_link = self.post_links[self.post_index] + 'liked_by/'

        likes = response.xpath(f'//a[@href="{like_by_link}"]//span/text()').get()
        if likes:
            likes_num = self.parse_number(likes)
        else:
            likes_num = 0

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
            'datetime': time_text
        }

        if self.post_index < len(self.post_links) - 1:
            self.post_index += 1
            yield self.get_post_detail_request(self.post_links[self.post_index])

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

        yield {
            'link': response.meta['link'],
            'followers': followers
        }

        if self.user_index < len(self.user_links) - 1:
            self.user_index += 1
            yield self.get_user_home_request(self.user_links[self.user_index])

    def start_requests(self):
        request = self.start_crawl_tag_home()

        if not request:
            request = self.start_crawl_post_detail()

        if not request:
            request = self.start_crawl_user_follower()

        if request:
            yield request