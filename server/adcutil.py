# -*- coding: utf-8 -*-
#
# アルゴリズムデザインコンテストのさまざまな処理

import numberlink
from datastore import *
from hashlib import sha1, sha256
from flask import make_response, render_template
import random
import datetime

#import pytz
from tz import UTC, JST
tz_utc = UTC()
tz_jst = JST()
def gae_datetime_JST(dt):
    "Google App Engineのtzinfo無しdatetimeを、UTCと見なしてそれをJSTに変換したのち、タイムスタンプ文字列として返す"
    dt_utc = dt.replace(tzinfo=tz_utc)
    dt_jst = dt_utc.astimezone(tz_jst)
    return dt_jst.strftime('%Y-%m-%d %H:%M:%S %Z%z')

def adc_response(msg, isjson, code=200, json_encoded=False):
    if json_encoded:
        body = msg
    else:
        template = 'response.json' if isjson else 'response.html'
        body = render_template(template, msg=msg)
    resp = make_response(body)
    if code == 200:
        resp.status = 'OK'
    elif code == 400:
        resp.status = 'Bad Request'
    elif code == 401:
        resp.status = 'Unauthorized'
    resp.status_code = code
    resp.headers['Content-Type'] = 'application/json' if isjson else 'text/html; charset=utf-8'
    return resp

def adc_response_text(body, code=200):
    resp = make_response(body)
    resp.status_code = code
    resp.headers['Content-Type'] = 'text/plain; charset=utf-8'
    return resp

def adc_response_json(body, code=200):
    resp = make_response(body)
    resp.status_code = code
    resp.headers['Content-Type'] = 'application/json'
    return resp

def adc_response_Q_data(result):
    "問題テキストデータを返す"
    if len(result) == 0:
        code = 404
        text = "Not Found\r\n"
    else:
        code = 200
        text = ""
        for data in result:
            text += data.text # 同じ番号で、複数あるのは、重複登録の場合
    return adc_response_text(text, code)


def log(username, what):
    root = log_key()
    i = Log(parent = root,
            username = username,
            what = what)
    i.put()

def log_get_or_delete(username=None, fetch_num=100, when=None, delete=False):
    query = Log.query(ancestor = log_key()).order(-Log.date)
    if username is not None:
        query = query.filter(Log.username == username)
    if when is not None:
        before = datetime.datetime.now() - when
        #print "before=", before
        query = query.filter(Log.date > before)
    q = query.fetch(fetch_num)
    results = []
    for i in q:
        if delete:
            tmp = { 'date': gae_datetime_JST(i.date) }
            i.key.delete()
        else:
            tmp = { 'date': gae_datetime_JST(i.date),
                    'username': i.username,
                    'what': i.what }
        results.append( tmp )
    return results


def adc_login(salt, username, password, users):
    tmp = salt + username + password
    hashed1 = sha1(tmp).hexdigest()  # 歴史的事情。もう消していいと思う
    hashed256 = sha256(tmp).hexdigest()
    # for u in users:
    #     #print "checking user=", u[0]
    #     if( username == u[0] and hashed == u[1] ):
    #         return u
    u = adc_get_user_info(username, users)
    if u is not None and u[1] in (hashed1, hashed256):
        return u
    else:
        return None

def adc_get_user_info(username, users):
    # まずはローカルに定義されたユーザを検索
    for u in users:
        if username == (u[0]):
            return u
    # 次に、データベースに登録されたユーザを検索
    res = get_userinfo(username)
    for r in res:
        return [r.username, r.password, r.displayname, r.uid, r.gid]
    return None

def adc_get_user_list(users):
    res = []
    # まずはローカルに定義されたユーザを検索
    for u in users:
        res.append(u[0])
    # 次に、データベースに登録されたユーザを検索
    res2 = get_username_list()
    res.extend(res2)
    return res

def insert_Q_data(q_num, text, author="DASymposium", year=2015, uniq=True):
    """
    問題データをデータベースに登録する。
    uniq==Trueのとき、q_numとauthorが重複する場合、登録は失敗する。
    """
    #重複チェック
    if uniq:
        q = get_user_Q_data(q_num, author, year)
        if 1 <= len(q):
            #for i in q: print "DUP",i
            return (False, "Error: data duplicated %d" % len(q)) # 重複エラー
    # 問題データのチェック
    (size, line_num, line_mat) = numberlink.read_input_data(text)
    r = numberlink.check_Q_data(size, line_num, line_mat)
    if not r:
        return (False, "Error: syntax error in data")
    # text2は、textを正規化したテキストデータ（改行コードなど）
    text2 = numberlink.generate_Q_data(size, line_num, line_mat)
    # rootエンティティを決める
    userinfo = get_userinfo(author)
    if len(userinfo) == 0:
        #root = qdata_key(year)
        return (False, "Error: user not found: %s" % author)
    else:
        root = userinfo[0].key
    # 問題データのエンティティ
    q = Question( parent = root,
                  qnum = q_num,
                  text = text2,
                  rows = size[1], # Y
                  cols = size[0], # X
                  linenum = line_num,
                  author = author )
    # 登録する
    q.put()
    #
    return (True, size, line_num)

def update_Q_data(q_num, text, author="DASymposium", year=2015):
    "問題データを変更する"
    # 問題データの内容チェック
    (size, line_num, line_mat) = numberlink.read_input_data(text)
    r = numberlink.check_Q_data(size, line_num, line_mat)
    text2 = numberlink.generate_Q_data(size, line_num, line_mat)
    # 既存のエンティティを取り出す
    res = get_user_Q_data(q_num, author, year)
    num = len(res)
    for i in res:
        i.text = text2
        i.put()
    return (num, size, line_num)

def get_Q_data(q_num, year=2015, fetch_num=5):
    "出題の番号を指定して、問題データをデータベースから取り出す"
    query = QuestionList.query(ancestor=qdata_key())
    query = query.filter(QuestionList.num==q_num)
    q = query.fetch()
    result = []
    for i in q: # 正常ならば1つだけのはず
        j = i.q.get() # Questionエンティティ
        result.append(j)
    return result

def get_Q_data_text(q_num, year=2015, fetch_num=5):
    "問題のテキストを返す"
    result = get_Q_data(q_num, year, fetch_num)
    text = None
    ret = False
    if len(result) == 1:
        text = result[0].text
        ret = True
    elif len(result) == 0:
        text = "Error: data not found: Q%d" % q_num
    else:
        text = "Error: duplicated data : Q%d %d" % (q_num, len(result))
    return ret, text

def get_user_Q_data(q_num, author, year=2015, fetch_num=99):
    "qnumとauthorを指定して問題データをデータベースから取り出す"
    userinfo = get_userinfo(author)
    if len(userinfo) == 0:
        root = qdata_key(year)
    else:
        root = userinfo[0].key
    query = Question.query( ancestor = root ).order(Question.qnum)
    #query = Question.query( ancestor = qdata_key(year) )
    query = query.filter( ndb.AND(Question.qnum == q_num,
                                  Question.author == author) )
    q = query.fetch(fetch_num)
    return q # qはリスト

def get_admin_Q_all():
    "データベースに登録されたすべての問題の一覧リスト"
    #query = Question.query().order(Question.author, Question.qnum)
    query = Question.query(ancestor=userlist_key()).order(Question.author, Question.qnum)
    q = query.fetch()
    num = len(q)
    out = str(num) + "\n"
    for i in q:
        dt = gae_datetime_JST(i.date)
        out += "Q%02d SIZE %dX%d LINE_NUM %d (%s) %s\n" % (i.qnum, i.cols, i.rows, i.linenum, i.author, dt)
    return out
    
def admin_Q_list_get():
    "コンテストの出題リストを取り出す"
    out = ""
    #userinfo = get_userinfo("administrator")
    #root = userinfo[0].key
    root = qdata_key()
    query = QuestionList.query(ancestor=root).order(QuestionList.num)
    q = query.fetch()
    for i in q:
        j = i.q.get()
        out += "%d %s %d" % (i.num, j.author, j.qnum) + "\n"
    return out

def admin_Q_list_create():
    "コンテスト用の出題リストを作成する"
    query = Question.query(ancestor=userlist_key()).order(Question.author, Question.qnum)
    qlist = []
    q = query.fetch()
    num = len(q)
    for i in q:
        qlist.append([i.qnum, i.author, i.key])
        #qlist.append(i.key)
    #print qlist
    random.shuffle(qlist)
    #print qlist
    out = str(num) + "\n"
    # parentをadministratorにしておこうか
    #userinfo = get_userinfo("administrator")
    #root = userinfo[0].key
    root = qdata_key()
    #既存の問題リストを削除する
    #query = QuestionList.query(ancestor=root)
    query = QuestionList.query()
    q = query.fetch()
    for i in q:
        i.key.delete()
    num = 1
    for i in qlist:
        eq = QuestionList( parent=root, q=i[2], num=num )
        eq.put()
        out += "%d %s %d" % (num, i[1], i[0]) + "\n"
        num += 1
    return out

def admin_Q_list_delete():
    "コンテストの出題リストを削除する"
    root = qdata_key()
    query = QuestionList.query(ancestor=root)
    q = query.fetch()
    num = 0
    for i in q:
        i.key.delete()
        num += 1
    return "DELETE %d" % num

def get_Q_all():
    "問題データの一覧リストを返す"
    # query = Question.query( ancestor = qdata_key() ).order(Question.qnum)
    # q = query.fetch()
    # num = len(q)
    # out = str(num) + "\n"
    # for i in q:
    #     print "out=", out
    #     out += "Q%02d SIZE %dX%d LINE_NUM %d (%s)\n" % (i.qnum, i.cols, i.rows, i.linenum, i.author)
    # return out
    query = QuestionList.query(ancestor=qdata_key()).order(QuestionList.num)
    q = query.fetch()
    num = len(q)
    out = "" #out = str(num) + "\n"
    for i in q:
        out += "Q%d\n" % i.num
        #j = i.q.get() # Questionエンティティ
        #out += "Q%02d SIZE %dX%d LINE_NUM %d (%s)\n" % (j.qnum, j.cols, j.rows, j.linenum, j.author)
    return out
    

def get_user_Q_all(author):
    "authorを指定して、問題データの一覧リストを返す"
    userinfo = get_userinfo(author)
    if len(userinfo) == 0:
        root = qdata_key(year)
    else:
        root = userinfo[0].key
    query = Question.query( ancestor = root ).order(Question.qnum)
    #query = query.filter(Question.author == author )
    q = query.fetch()
    num = len(q)
    out = ""
    for i in q:
        out += "Q%d SIZE %dX%d LINE_NUM %d (%s)\n" % (i.qnum, i.cols, i.rows, i.linenum, i.author)
    return out



def delete_Q_data(q_num):
    "問題の番号を指定して、問題データをデータベースから削除する"
    res = get_Q_data(q_num)
    num = len(res)
    for i in res:
        i.key.delete()
    return num

def delete_user_Q_data(q_num, author, year=2015):
    "qnumとauthorを指定して、問題データをデータベースから削除する"
    res = get_user_Q_data(q_num, author, year)
    msg = ""
    if len(res) == 0:
        msg = "Q data not found"
    else:
        for i in res:
            msg += "DELETE /user/%s/Q/%d\n" % (author, i.qnum)
            i.key.delete()
    return msg


def get_admin_A_all():
    "データベースに登録されたすべての回答データの一覧リスト"
    query = Answer.query(ancestor=userlist_key()).order(Answer.owner, Answer.anum)
    q = query.fetch()
    num = len(q)
    out = str(num) + "\n"
    for i in q:
        dt = gae_datetime_JST(i.date)
        out += "A%02d (%s) %s\n" % (i.anum, i.owner, dt)
    return out

    
def get_A_data(a_num=None, username=None):
    "データベースから回答データを取り出す"
    if username is None:
        root = userlist_key()
    else:
        userinfo = get_userinfo(username)
        if len(userinfo) != 1:
            msg = "ERROR: user not found: %s" % username
            return False, msg, None
        root = userinfo[0].key
    query = Answer.query(ancestor=root).order(Answer.anum)
    if a_num is not None:
        query = query.filter(Answer.anum == a_num)
    q = query.fetch()
    return True, q, root

    
def put_A_data(a_num, username, text):
    "回答データをデータベースに格納する"
    msg = ""
    # 出題データを取り出す
    ret, q_text = get_Q_data_text(a_num)
    if not ret:
        msg = "Error in Q%d data: " % a_num + q_text
        return False, msg
    # 重複回答していないかチェック
    ret, q, root = get_A_data(a_num, username)
    if ret==True and 0 < len(q):
        msg += "ERROR: duplicated answer\n";
        return False, msg
    # 回答データのチェックをする
    judges, msg = numberlink.check_A_data(text, q_text)
    if len(judges)==0 or judges[0] == False: # 2つ以上にはならないはず
        msg += "Error in answer A%d\n" % a_num
        check_A = False
    else:
        check_A = True # 正解
    # 採点する  ★未実装
    if check_A:
        msg += "Get 3.141592 point [DUMMY]\n"
    else:
        msg += "Get 0 point [DUMMY]\n"
    # データベースに登録する。不正解でも登録する
    a = Answer( parent = root,
                anum = a_num,
                text = text,
                owner = username )
    a_key = a.put()
    ai = AnswerInfo( parent = a_key,
                     anum = a_num,
                     result = msg ) # とりあえず
    ai.put()
    return True, msg

def put_A_info(a_num, username, info):
    "回答データの補足情報をデータベースに格納する"
    msg = ""
    # 回答データを取り出す。rootはUserInfoのkey、q[0]はAnswer
    ret, q, root = get_A_data(a_num, username)
    if ret==False or len(q)==0:
        if ret==False: msg += q + "\n"
        msg += "ERROR: A%d data not found" % a_num
        return False, msg
    # 重複登録しないようにチェック
    query = AnswerInfo.query(ancestor=q[0].key)
    query = query.filter(AnswerInfo.anum == a_num) # 必ず一致するはずだが
    q2 = query.fetch()
    if len(q2) == 0:
        # 新規登録する
        ai = AnswerInfo( parent = q[0].key, # Answerの下に
                         anum = a_num,
                         cpu_sec = info['cpu_sec'],
                         mem_byte = info['mem_byte'],
                         misc_text = info['misc_text'] )
        ai.put()
        msg += "INSERT A%d info\n" % a_num
    else:
        for i in q2:
            #i.key.delete()
            i.cpu_sec = info['cpu_sec']
            i.mem_byte = info['mem_byte']
            i.misc_text = info['misc_text']
            i.put()
            msg += "UPDATE A%d info\n" % i.anum
            # エンティティは1個だけのはずなのでループ回数は1のはず
    return True, msg

def get_or_delete_A_data(a_num=None, username=None, delete=False):
    "回答データをデータベースから、削除or取り出し"
    ret, q, root = get_A_data(a_num=a_num, username=username)
    if not ret:
        return False, q # q==msg
    if len(q)==0:
        return ret, q
    result = []
    if delete:
        for i in q: # 正常ならば1個しかないはず
            get_or_delete_A_info(a_num=a_num, username=username, delete=True)
            result.append("DELETE A%d" % i.anum)
            i.key.delete()
    else: # GETの場合
        for i in q: # 正常ならば1個しかないはず
            result.append(i.text)
    return True, result

def get_or_delete_A_info(a_num=None, username=None, delete=False):
    "回答データの補足情報をデータベースから、削除or取り出し"
    msg = ""
    root = userlist_key()
    if username is not None:
        userinfo = get_userinfo(username)
        if len(userinfo) != 1:
            msg = "ERROR: user not found: %s" % username
            return False, msg, None
        root = userinfo[0].key
    # AnswerInfoデータを取り出す
    query = AnswerInfo.query(ancestor=root)
    if a_num is not None:
        query = query.filter(AnswerInfo.anum == a_num)
    q = query.fetch()
    results = []
    num = 0
    for i in q:
        num += 1
        if delete:
            results.append({'anum': i.anum})
            i.key.delete()
        else:
            results.append( i.to_dict() )
    method = 'DELETE' if delete else 'GET'
    a_num2 = 0 if a_num is None else a_num
    msg += "%s A%d info %d" % (method, a_num2, num)
    return True, msg, results

def create_user(username, password, displayname, uid, gid, salt):
    "ユーザーをデータベースに登録"
    tmp = salt + username + password
    hashed = sha256(tmp).hexdigest()
    userlist = userlist_key()
    u = UserInfo( parent = userlist,
                  username = username,
                  password = hashed,
                  displayname = displayname,
                  uid = uid,
                  gid = gid )
    u.put()

def get_username_list():
    "ユーザー名の一覧リストをデータベースから取り出す"
    query = UserInfo.query( ancestor = userlist_key() ).order(UserInfo.uid)
    q = query.fetch()
    res = []
    for u in q:
        res.append(u.username)
    return res

def get_userinfo(username):
    "ユーザー情報をデータベースから取り出す"
    query = UserInfo.query( ancestor = userlist_key() ).order(UserInfo.uid)
    query = query.filter(UserInfo.username == username)
    q = query.fetch()
    return q

def delete_user(username):
    "ユーザーをデータベースから削除"
    users = get_userinfo(username)
    n = len(users)
    for u in users: # オブジェクトが複数返ってくるのは本来おかしい
        u.key.delete()
    return n