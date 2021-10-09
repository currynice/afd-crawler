# -*- coding: utf-8 -*-
# !/usr/bin/python
"""=========================================
@author: cxy
@file: afd_crawler.py
@create_time: 2021/10/08 09:49
@file specification: 爱发电爬取脚本
    
    流程： 登录账号(不保存) -- 获取发电列表 -- 循环读取每个的内容 -- 将节目保存下来，mp4转换为mp3
========================================="""
import time
import datetime
import requests
import re
from copy import deepcopy
import logging
import os
import pathlib


# 定义日志相关内容
logging.basicConfig(format='%(asctime)s - %(pathname)s[line:%(lineno)d] - %(levelname)s: %(message)s',
                    level=logging.INFO)
handler = logging.FileHandler(filename='afd_crawler.log', mode='w', encoding='utf-8')
log = logging.getLogger(__name__)
log.addHandler(handler)

# 定义全局变量
FINISH_ARTICLES = []
ALL_ARTICLES = []


class RequestError(Exception):
    """ 请求错误 """
    pass


class NotValueError(Exception):
    """ 没有内容错误 """
    pass


def _load_finish_article():
    """ 将已经下好的节目 ID 加载到内存中 """
    result = []
    _dir = pathlib.PurePosixPath()
    file_path = os.path.abspath(_dir / 'finished.txt')
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            for article_id in f.readlines():
                article_id = article_id.strip('\n')
                if article_id:
                    result.append(article_id)
    return list(set(result))


def _save_finish_article_id_to_file():
    """ 记录已经下好的节目 ID """
    global FINISH_ARTICLES
    _dir = pathlib.PurePosixPath()
    file_path = os.path.abspath(_dir / 'finished.txt')
    with open(file_path, 'a+', encoding='utf-8') as f:
        for i in FINISH_ARTICLES:
            f.write(str(i) + '\n')


def check_filename(file_name):
    """
    校验文件名称的方法，在 windows 中文件名不能包含('\','/','*','?','<','>','|') 字符
    Args:
        file_name: 文件名称
    Returns:
        修复后的文件名称
    """
    return file_name.replace('\\', '') \
                    .replace('/', '') \
                    .replace('*', 'x') \
                    .replace('?', '') \
                    .replace('<', '《') \
                    .replace('>', '》') \
                    .replace('|', '_') \
                    .replace('\n', '') \
                    .replace('\b', '') \
                    .replace('\f', '') \
                    .replace('\t', '') \
                    .replace('\r', '')


class Cookie:
    def __init__(self, cookie_string=None):
        self._cookies = {}
        if cookie_string:
            self.load_string_cookie(cookie_string)

    @property
    def cookie_string(self):
        """
        将对象的各属性转换成字符串形式的 Cookies
        Returns:
            字符串形式的 cookies，方便给 HTTP 请求时使用
        """
        return ';'.join([f'{k}={v}' for k, v in self._cookies.items()])

    def set_cookie(self, key, value):
        self._cookies[key] = value

    @staticmethod
    def list_to_dict(lis):
        """
        列表转换成字典的方法
        Args:
            lis: 列表内容
        Returns:
            转换后的字典
        """
        result = {}
        for ind in lis:
            try:
                ind = ind.split('=')
                result[ind[0]] = ind[1]
            except IndexError:
                continue
        return result

    def load_string_cookie(self, cookie_str):
        """
        从字符串中加载 Cookie 的方法（将字符串转换成字典形式）, 相当于 cookie_string 方法的逆反操作
        Args:
            cookie_str: 字符串形式的 Cookies，一般是从抓包请求中复制过来
                eg: gksskpitn=cc662cd7-0a39-430a-a603-a1c61d6f784f; LF_ID=1587783958277-6056470-8195597;
        Returns:
        """
        cookie_list = cookie_str.split(';')
        res = self.list_to_dict(cookie_list)
        self._cookies = {**self._cookies, **res}

    def load_set_cookie(self, set_cookie):
        """
        从抓包返回的 Response Headers 中的 set-cookie 中提取 cookie 的方法
        Args:
            set_cookie: set-cookie 的值
        Returns:
        """
        set_cookie = re.sub(".xpires=.*?;", "", set_cookie)
        cookies_list = set_cookie.split(',')
        cookie_list = []
        for cookie in cookies_list:
            cookie_list.append(cookie.split(';')[0])
        res = self.list_to_dict(cookie_list)
        self._cookies = {**self._cookies, **res}

    def __repr__(self):
        return f'The cookies is : {self._cookies}'


class GeekCrawler:
    """ afd相关操作的类 """
    def __init__(self, cellphone=None, passwd=None,auth_code=None, exclude=None):
        self.cellphone = cellphone
        self.password = passwd
        self._check()
        self.cookie = Cookie("")
        self.common_headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Pragma": "no-cache",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) "
                          "AppleWebKit/537.36 (KHTML, like Gecko)Chrome/81.0.4044.122 Safari/537.36"
        }
        self.products = []
        self.exclude = exclude
        self.auth_code = auth_code

    def _check(self):
        if not self.cellphone:
            self.cellphone = str(input('请输入你要登录的手机号： '))
        if not self.password:
            self.password = str(input('请输入你的密码： '))

    def _login(self):
        """ 登录接口方法 """
        log.info("请求登录接口：")
        url = "https://afdian.net/api/passport/login"
        method = "POST"
        headers = deepcopy(self.common_headers)
        headers["Host"] = "afdian.net"
        headers["Origin"] = "https://afdian.net"
        headers["Cookie"] = self.cookie.cookie_string
        params = {
            "account": self.cellphone,
            "password": self.password
        }

        log.info(f"接口请求参数：{params}")
        res = requests.request(method, url, headers=headers, json=params)

        if (res.status_code != 200) or (str(res.json().get('code', '')) == '-1'):
            _save_finish_article_id_to_file()
            log.info(f"此时 products 的数据为：{self.products}")
            log.error(f"登录接口请求出错，返回内容为：{res.content.decode()}")
            raise RequestError(f"登录接口请求出错，返回内容为：{res.content.decode()}")
        self.auth_token = res.json().get('data', {}).get('auth_token')
        log.info(self.auth_token)
        self.cookie.set_cookie('auth_token' ,self.auth_token)
        log.info(self.cookie.cookie_string)
        log.info('-'*40)

    def _user_auth(self):
        """ 用户认证接口方法 """
        log.info("请求用户认证接口：")
        now_time = int(time.time() * 1000)
        url = f"https://afdian.net/api/my/account"
        method = "GET"
        headers = deepcopy(self.common_headers)
        headers["Host"] = "afdian.net"
        headers["Origin"] = "https://afdian.net"
        headers["Cookie"] = self.cookie.cookie_string

        res = requests.request(method, url, headers=headers)

        if (res.status_code != 200) or (str(res.json().get('code', '')) != '0'):
            _save_finish_article_id_to_file()
            log.info(f"此时 products 的数据为：{self.products}")
            log.error(f"用户认证接口请求出错，返回内容为：{res.json()}")
            raise RequestError(f"用户认证接口请求出错，返回内容为：{res.json()}")
        self.cookie.load_set_cookie(res.headers['Set-Cookie'])
        log.info('-' * 40)


    def _product(self):
        """ 获得所有节目的方法 """
        log.info("请求获取目录接口："+self.cookie.cookie_string)
        url = "https://afdian.net/api/user/get-album-catalog?album_id=c6ae1166a9f511eab22c52540025c377"
        method = "GET"
        headers = deepcopy(self.common_headers)
        headers["Host"] = "afdian.net"
        headers["Origin"] = "https://afdian.net"
        headers["Cookie"] = self.cookie.cookie_string
        params = {}

        res = requests.request(method, url, headers=headers, json=params)

        if res.status_code != 200:
            log.info(f"此时 节目 的数据为：{self.products}")
            log.error(f"节目目录列表接口请求出错，返回内容为：{res.content.decode()}")
            raise RequestError(f"节目目录列表接口请求出错，返回内容为：{res.content.decode()}")
        data = res.json().get('data', {})
        # self.cookie.load_set_cookie(res.headers['Set-Cookie'])
        if data:
            self.products += self._parser_products(data)
        else:
            _save_finish_article_id_to_file()
            log.info(f"此时 节目 的数据为：{self.products}")
            log.error(f"节目目录列表接口没有获取到内容，请检查请求。返回结果为：{res.content.decode()}")
            raise NotValueError(f"节目目录列表接口没有获取到内容，请检查请求。返回结果为：{res.content.decode()}")
        log.info('-' * 40)

        for pro in self.products:
            postId = pro['post_id']
            title = pro['title']
            audio_url = pro['audio']
            log.info('下载'+title)
            self.save_to_file(
                dir_name='跟宇宙结婚',
                filename=title,
                audio=audio_url,
                file_type=file_type
            )


    def _parser_products(self, data):
        """
        解析（从中提取部分数据）
        Args:
            data: 节目相关信息，一般为接口返回的数据
         
        Returns:
            解析后的结果，以列表形式
        """
        result = []
      
        keys = ['title', 'post_id', 'audio']  # 定义出要拿取的字段

        lists = data.get('list', {})
        for each in lists:
            # 如果课程标题在需要排除的列表中，则跳过该课程
            # if each.get('post_id', '') in self.exclude:
            #     continue

        #     new_product = {key: value for key, value in each if key in keys}
        #     new_product['articles'] = []  # 定义文章列表（用来存储文章信息）
        #     new_product['article_ids'] = []  # 定义文章 ID 列表（用来存储文章 ID 信息） ）
           dict = {'title': 'title_', 'post_id': 'post_id_', 'audio': 'audio_'}
           dict['title'] = each.get('title')
           dict['post_id'] = each.get('post_id')
           dict['audio'] = each.get('audio')
           result.append(dict)
          
        return result


    

    @staticmethod
    def save_to_file(dir_name, filename, audio=None, file_type=None):
        """
        将结果保存成文件的方法，保存在当前目录下
        Args:
            dir_name: 文件夹名称，如果不存在该文件夹则会创建文件夹
            filename: 文件名称，直接新建

            audio: 需要填入文件中的音频文件（一般为音频地址）
            file_type: 文档类型（需要保存什么类型的文档），默认保存为 Markdown 文档
        Returns:
        """
        if not file_type: file_type = '.mp4'
        dir_path = pathlib.PurePosixPath() / dir_name
        if not os.path.isdir(dir_path):
            os.mkdir(dir_path)
        filename = check_filename(filename) + file_type
        file_path = os.path.abspath(dir_path / (filename + file_type))

        DownloadFile(audio,dir_name,filename)

        # 将所有数据写入文件中
        # with open(file_path, 'w', encoding='utf-8') as f:
        #     if audio:
        #         audio_text = f'<audio title="{filename}" src="{audio}" controls="controls"></audio> \n'
        #         f.write(audio_text)


def DownloadFile(url, dir_name,file_name):
    try:
        if url is None or dir_name is None or file_name is None:
            print('参数错误')
            return None
        # 文件夹不存在，则创建文件夹
        folder = os.path.exists(dir_name)
        if not folder:
            os.makedirs(dir_name)
        # 读取资源
        res = requests.get(url,stream=True)
        # 获取文件地址
        file_path = os.path.join(dir_name, file_name)
        print('开始写入文件：', file_path)
        # 打开本地文件夹路径file_path，以二进制流方式写入，保存到本地
        with open(file_path, 'wb') as fd:
            for chunk in res.iter_content():
                fd.write(chunk)
        print(file_name+' 成功下载！')
    except:
        print("程序错误")


def run(cellphone=None, passwd=None, exclude=None, file_type=None):
    """ 整体流程的请求方法 """
    global FINISH_ARTICLES
    global ALL_ARTICLES

    geek = GeekCrawler(cellphone, passwd, exclude=exclude)
    geek._login()  # 请求登录接口进行登录
    geek._product()  # 请求获取发电接口 todo 暂时写死

       
    _save_finish_article_id_to_file()
    log.info("正常抓取完成。")   


if __name__ == "__main__":
   # 采用在脚本中写死账号密码的方式
    # cellphone = "*"
    # passwd = "*"

    # 采用每次跑脚本手动输入账号密码的方式
    cellphone = str(input("请输入你的账号（手机号）: "))
    passwd = str(input("请输入你的密码: "))

    # 需要排除的节目id
    # exclude = ['sx1', 'sx2']
    exclude = []

    # 保存文件的后缀名
    file_type = '.mp4'


    try:
        FINISH_ARTICLES = _load_finish_article()
        run(cellphone, passwd, exclude, file_type)
    except Exception:
        import traceback
        log.error(f"请求过程中出错了，出错信息为：{traceback.format_exc()}")
    finally:
        _save_finish_article_id_to_file()