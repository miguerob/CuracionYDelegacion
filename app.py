import os
from flask import Flask, jsonify, request, render_template
from hive.hive import Hive
from hive.blockchain import Blockchain
from hive.account import Account
import time
import datetime
import uuid
import random
import string
import json

from lib import db
from lib import api
from lib import errorHandler
from lib.errors import CurangelError
from lib.account_util import Account

from lib.rate_limit import Enforcer, RateLimitError
from lib.db_util import QueueDBHelper

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    userid   = uuid.uuid4().hex
    username = request.form['username']
    userhash = request.form['userhash']

    userip   = '0.0.0.0'

    # save a new entry
    if username and userhash:
        # check if user exists
        results = db.select('users',['account'],{'account':username},'account')
        if len(results) > 0:
            errorHandler.throwError("User already registered")
        # write
        db.insert('users',{'id': userid, 'account': username, 'hash': userhash, 'ip': userip})
    else:
        errorHandler.throwError("Unsufficient userdata to register")
    api.output({'status':'success'})
    return "Hello {}!"

@app.route('/login', methods=['GET', 'POST'])
def login():
    hived_nodes = [
        'https://api.pharesim.me',
        'https://anyx.io',
        'https://api.hive.blog',
        'https://api.openhive.network',
    ]
    client = Hive(nodes=hived_nodes)
    # output variable
    user = {}
    username = request.form['username']
    userhash = request.form['userhash']
    results = db.select('users',['account','hash','admin','curator'],{'account':username},'account')
    if len(results) > 0:
        if results[0]['hash'] == userhash:
            user['account']   = username
            user['admin']     = results[0]['admin']
            user['curator']   = results[0]['curator']
            user['delegator'] = 0

            delegations = client.get_vesting_delegations(username,'criptomonedastv',1)
            if len(delegations) > 0 and delegations[0]['delegatee'] == 'criptomonedastv':
                user['delegator'] = 1
        else:
            errorHandler.throwError('Login failed')
    else:
        errorHandler.throwError('Unknown user')
    api.output(user)
    return user

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    hived_nodes = [
        'https://api.pharesim.me',
        'https://anyx.io',
        'https://api.hive.blog',
        'https://api.openhive.network',
    ]
    client = Hive(nodes=hived_nodes)
    # output variable
    data = {}
    # get and set variables
    username  = None
    userhash  = None
    switch    = None
    account   = None
    deleteuv  = None
    blacklist = None
    reason    = None
    deletebl  = None
    deletedv  = None
    if 'username' in request.form:
        username  = request.form['username']
    if 'userhash' in request.form:
        userhash  = request.form['userhash']
    if 'switch' in request.form:
        switch    = request.form['switch']
    if 'account' in request.form:
        account   = request.form['account']
    if 'deleteupvote' in request.form:
        deleteuv  = request.form['deleteupvote']
    if 'blacklist' in request.form:
        blacklist = request.form['blacklist']
    if 'reason' in request.form:
        reason    = request.form['reason']
    if 'deleteblacklist' in request.form:
        deletebl  = request.form['deleteblacklist']
    if 'deletedownvote' in request.form:
        deletedv  = request.form['deletedownvote']
    # check permissions
    results = db.select('users',['admin'],{'account':username,'hash':userhash,'admin':1},'account')
    if len(results) < 1 or results[0]['admin'] == 0:
        errorHandler.throwError('No permission')
    if switch:
        if switch == 'admin' or switch == 'delete':
            results = db.select('users',['admin'],'1=1','id')
            if len(results) < 2:
                errorHandler.throwError('There has to be one admin')
        if switch == 'delete':
            db.delete('users',{'id':account})
        else:
            results = db.select('users',[switch],{'id':account},switch)
            if results[0][switch] == 1:
                new = 0
            else:
                new = 1
            db.update('users',{switch:new},{'id':account})
        data['status'] = 'success'
    elif deleteuv:
        post = db.select('upvotes',['status'],{'id':deleteuv},'id')
        if post[0]['status'] == 'in queue':
            db.delete('upvotes',{'id':deleteuv})
            data['status'] = 'success'
        else:
            errorHandler.throwError('Only posts in queue can be removed from the queue. Duh!')
    elif blacklist:
        if reason:
            bl = db.select('blacklist',['user'],{'user':blacklist},'id')
            if len(bl) > 0:
                errorHandler.throwError('User is already blacklisted.')
            db.insert('blacklist',{'id':uuid.uuid4().hex,'user':blacklist,'reason':reason,'account':username})
            data['status'] = 'success'
        else:
            errorHandler.throwError('You need to give a reason for blacklisting')
    elif deletebl:
        db.delete('blacklist',{'id':deletebl})
        data['status'] = 'success'
    elif deletedv:
        post = db.select('downvotes',['status'],{'id':deletedv},'id')
        if post[0]['status'] == 'wait':
            db.delete('downvotes',{'id':deletedv})
            data['status'] = 'success'
        else:
            errorHandler.throwError('Only posts that are waiting for a downvote can be removed. Duh!')
    else:
        # get users
        results = db.select('users',['id','account','curator','admin','created'],'1=1','created DESC')
        users = []
        for row in results:
            user = dict(row)
            user['delegator'] = 0
            delegations = client.get_vesting_delegations(user['account'],'criptomonedastv',1)
            if len(delegations) > 0 and delegations[0]['delegatee'] == 'criptomonedastv':
                user['delegator'] = 1
            users.append(user)
        data['users'] = users
        # get upvotes
        upvotes = []
        results = db.select('upvotes',['id','account','created','link','user','category','slug','title','type','payout','status','reward_sp'],'1=1','created DESC')
        for row in results:
            upvotes.append(dict(row))
        data['upvotes'] = upvotes
        # get blacklist
        blacklist = []
        results = db.select('blacklist',['id','user','reason','created','account'],'1=1','created DESC')
        for row in results:
            blacklist.append(dict(row))
        data['blacklist'] = blacklist
        # get downvotes
        downvotes = []
        results = db.select('downvotes',['id','created','account','reason','link','user','category','slug','title','type','payout','maxi','status'],'1=1','created DESC')
        for row in results:
            downvotes.append(dict(row))
    data['downvotes'] = downvotes
    api.output(data)
    return data

@app.route('/downvote', methods=['GET', 'POST'])
def downvote():
    hived_nodes = [
        'https://api.pharesim.me',
        'https://anyx.io',
        'https://api.hive.blog',
        'https://api.openhive.network',
    ]
    client = Hive(nodes=hived_nodes)
    chain = Blockchain(client)

    # whitelist
    whitelist = [
        'pharesim','azircon','nikv','tazi','galenkp','joshmania','lemony-cricket'
    ]

    # output variable
    data = {}

    # get and set variables
    username  = None
    userhash  = None
    postlink = None
    limit = None
    reason = None
    deletedv = None
    if 'username' in request.form:
        username  = request.form['username']
    if 'userhash' in request.form:
        userhash  = request.form['userhash']
    if 'postlink' in request.form:
        postlink = request.form['postlink']
    if 'limit' in request.form:
        limit    = request.form['limit']
    if 'reason' in request.form:
        reason   = request.form['reason']
    if 'deletedownvote' in request.form:
        deletedv = request.form['deletedownvote']
    
    # check permissions
    results = db.select('users',['id'],{'account':username,'hash':userhash},'id')
    delegator = 0
    delegations = client.get_vesting_delegations(username,'criptomonedastv',1)
    if len(delegations) > 0 and delegations[0]['delegatee'] == 'criptomonedastv':
        delegator = 1
    if len(results) < 1 or delegator == 0:
        errorHandler.throwError('No permission')
        
    if limit:
        limit = int(limit)
    
    if deletedv:
        post = db.select('downvotes',['status'],{'account':username,'id':deletedv},'status')
        if len(results) < 1:
            errorHandler.throwError('Downvote not found!')
        db.delete('downvotes',{'id':deletedv})
        data['status'] = 'success'
    else:
        # submit new post
        if postlink:
            link = postlink.split('#')
            if len(link) > 1:
                link = link[1].split('/')
            else:
                link = postlink.split('/')
            post = client.get_content(link[-2][1:],link[-1])
            # check if reason was given
            if not reason:
                errorHandler.throwError('You need to give a reason for the downvote.')
            # check whitelist
            if username not in whitelist:
                errorHandler.throwError('To use this tool, please apply in our Discord!')
            # check if user has more than the limit of posts waiting
    #       result = db.select('downvotes',['id'],{'account':username,'status':'wait'},'id')
    #       if len(result) > 2:
    #           errorHandler.throwError('You already have '+len(result)+' posts waiting to be downvoted. Please wait until those are processed.')

            # check if post is in upvote queue
            result = db.select('upvotes',['account'],{'slug':post['permlink'],'status':'in queue'},'id')
            if len(result) > 0:
                errorHandler.throwError('Post was already curated by '+result[0]['account'])

            # check if already voted
            for vote in post['active_votes']:
                if vote['voter'] == 'criptomonedastv':
                    errorHandler.throwError('We already voted on that post.')

            # check if user added that post already
            result = db.select('downvotes',['id'],{'account':username,'link':post['url'],'status':'wait'},'id')
            if len(result) > 0:
                errorHandler.throwError('You already added this post. Re-adding it would not change anything. If you want to maximize your power on this post, do not add others in this round.')

            # check cashout time
            cashoutts = time.mktime(datetime.datetime.strptime(post['cashout_time'], "%Y-%m-%dT%H:%M:%S").timetuple())
            chaints = time.mktime(datetime.datetime.strptime(chain.info()['time'], "%Y-%m-%dT%H:%M:%S").timetuple())
            if cashoutts - chaints < 60*60*24:
                errorHandler.throwError('Cashout of post in less than 24 hours. Will not add to queue.')

            # check if limit is valid
            if limit < 10 or limit > 99:
                errorHandler.throwError('Invalid limit for downvote weight.')
            targetreward = round(float(post['pending_payout_value'][:-4]) * (100-limit) / 100, 3)
            post_type = 1
            if post['parent_author']:
                post_type = 2
            db.insert('downvotes',{'id':uuid.uuid4().hex, 'account': username, 'reason': reason, 'link': post['url'], 'user': post['author'], 'category': post['category'], 'slug': post['permlink'], 'title': post['title'], 'type': post_type, 'payout': post['cashout_time'], 'status': 'wait', 'reward': post['pending_payout_value'], 'maxi': targetreward})

        # get downvotes
        downvotes = []
        results = db.select('downvotes',['id','created','reason','link','user','category','slug','title','type','payout','status','reward','maxi'],{'account':username},'created DESC')
        for row in results:
            downvotes.append(dict(row))
        data['downvotes'] = downvotes
    api.output(data)
    return data

@app.route('/upvote', methods=['GET', 'POST'])
def upvote():
    hived_nodes = [
    'https://api.pharesim.me',
    'https://anyx.io',
    'https://api.hive.blog',
    'https://api.openhive.network',
    ]
    credfile = open("credentials.txt")
    user = credfile.readline().strip()
    key = credfile.readline().strip()
    client = Hive(keys=[key],nodes=hived_nodes)
    chain = Blockchain(client)
    # output variable
    data = {}
    username  = None
    userhash  = None
    postlink = None
    deleteuv = None
    if 'username' in request.form:
        username  = request.form['username']
    if 'userhash' in request.form:
        userhash  = request.form['userhash']
    if 'postlink' in request.form:
        postlink = request.form['postlink']
    if 'deleteupvote' in request.form:
        deleteuv = request.form['deleteupvote']
    # check permissions
    results = db.select('users',['id'],{'account':username,'hash':userhash,'curator':1},'id')
    if len(results) < 1:
        errorHandler.throwError('No permission')

    # delete post
    if deleteuv:
        post = db.select('upvotes',['status'],{'account':username,'id':deleteuv},'status')
        if len(results) < 1:
            errorHandler.throwError('Upvote not found!')
        db.delete('upvotes',{'id':deleteuv})
        data['status'] = 'success'
    else:
        # submit new post
        if postlink:
            link = postlink.split('#')
            if len(link) > 1:
                link = link[1].split('/')
            else:
                link = postlink.split('/')

            post = client.get_content(link[-2][1:],link[-1])
            chaininfo = chain.info()

            # check if curator is author himself
            if post['author'] == username:
                errorHandler.throwError('Curating your own post? Are you serious?')

            # check if curator is author himself
            if post['author'] == 'criptomonedastv':
                errorHandler.throwError('We do not vote for ourselves :D')

            # check if cross post
            metadata = post['json_metadata']
            if metadata != '':
                metadata = json.loads(metadata)
                if 'tags' in metadata:
                    if 'cross-post' in metadata['tags']:
                        errorHandler.throwError('This is a cross-post. We do not vote on those.')
            
            # check if author used bitbots
            # bidbots = ['alfanso','appreciator','bdvoter','bid4joy','boomerang','booster','bot-api','brandonfrye','buildawhale','edensgarden','inciter','joeparys','leo.voter','luckyvotes','minnowbooster','minnowhelper','minnowvotes','ocdb','onlyprofitbot','postpromoter','profitvote','promobot','qustodian','redlambo','rocky1','sct.voter','smartmarket','smartsteem','sneaky-ninja','sportsvoter','spydo','steemyoda','thebot','therising','tipu','treeplanter','triplea.bot','unknownonline','upmewhale','upmyvote','whalepromobot']
            # account = Account(post['author'],client)
            # history = account.get_account_history(-1,2500,filter_by='transfer')
            # for h in history:
            #     if h['memo'][:4] == 'http' and h['to'] in bidbots:
            #         notification = ''
            #         notified = db.select('upvote_notifications',['user'],{'user':post['author'],'created >':"datetime('now','-7 days')",'reason':'bidbot'},'created')
            #         if len(notified) < 1:
            #             db.insert('upvote_notifications',{'id':uuid.uuid4().hex,'user':post['author'],'reason':'bidbot'})
            #             notification = ' User has received a comment.'
            #             permlink = ''.join(random.sample(string.ascii_lowercase, k=10))
            #             body = "Great work! Your post was selected for curation by one of @criptomonedastv's dedicated curators for its contribution to quality!\n<br />"
            #             body += "...unfortunately, it had to be excluded from curation because you recently bought a vote from a bid bot ("+h['to']+")."
            #             body += "Authors who participate in vote buying are not eligible for our votes.\n<br />"
            #             body += "But don't worry. It only takes 7 days of not buying votes to be able to receive our vote again, so maybe one of your next posts will make it!\n<br />"
            #             body += "Take care and hive five!"
            #             client.commit.post('Re: '+post['title'], body, 'criptomonedastv', permlink=permlink, reply_identifier='@'+post['author']+'/'+post['permlink'])
            #         errorHandler.throwError('User has used a bid bot recently. Will not add to queue.'+notification)
            #     last = h['timestamp']
            #     txts = time.mktime(datetime.datetime.strptime(h['timestamp'], "%Y-%m-%dT%H:%M:%S").timetuple())
            #     chaints = time.mktime(datetime.datetime.strptime(chaininfo['time'], "%Y-%m-%dT%H:%M:%S").timetuple())
            #     if chaints - txts > 60*60*24*7:
            #         break

            # check if author used liquifier
            liquifiers = ['likwid','reward.app']
            beneficiaries = post['beneficiaries']
            notification = ''
            for b in beneficiaries:
                if b['account'] in liquifiers:
                    notified = db.select('upvote_notifications',['user'],{'user':post['author'],'reason':'liquifier'},'created')
                    if len(notified) < 1:
                        db.insert('upvote_notifications',{'id':uuid.uuid4().hex,'user':post['author'],'reason':'liquifier'})
                        notification = ' User has received a comment.'
                        permlink = ''.join(random.sample(string.ascii_lowercase, k=10))
                        body = "Great work! Your post was selected for curation by one of @criptomonedastv's dedicated curators for its contribution to quality!\n<br />"
                        body += "...unfortunately, it had to be excluded from curation because of the use of a service ("+b['account']+") to liquify rewards."
                        body += "Our upvotes are reserved for content which is created with a commitment to long term growth and decentralization of Hive Power.\n<br />"
                        body += "This exclusion only applies to this and eventually other future liquified posts and not all your publications in general. \n<br />"
                        body += "Take care and hive five!"
                        client.commit.post('Re: '+post['title'], body, 'criptomonedastv', permlink=permlink, reply_identifier='@'+post['author']+'/'+post['permlink'])
                    errorHandler.throwError('Post is using a liquifier ('+b['account']+') for rewards. Will not add to queue.'+notification)


            # check if already voted
            for vote in post['active_votes']:
                if vote['voter'] == 'criptomonedastv':
                    errorHandler.throwError('We already voted on that post.')

            # check if post has a lot of rewards already
            if float(post['pending_payout_value'][:-4]) >= 10:
                errorHandler.throwError('This post has quite a bit of recognition already. Please curate content which really needs a boost, there are many posts which receive next to nothing!')

            # check if exists in upvote queue
            results = db.select('upvotes',['id'],{'user':post['author'],'slug':post['permlink'],'status !': 'canceled'},'id')
            if len(results) > 0:
                errorHandler.throwError('This post has been submitted before. Will not add to queue again.')

            # check if exists in downvote queue
            result = db.select('downvotes',['account'],{'slug':post['permlink'],'status':'wait'},'id')
            if len(result) > 0:
                errorHandler.throwError('Post was already marked for downvote by '+result[0]['account'])

            # check cashout time
            cashoutts = time.mktime(datetime.datetime.strptime(post['cashout_time'], "%Y-%m-%dT%H:%M:%S").timetuple())
            chaints = time.mktime(datetime.datetime.strptime(chaininfo['time'], "%Y-%m-%dT%H:%M:%S").timetuple())
            if cashoutts - chaints < 60*60*36:
                errorHandler.throwError('Cashout of post in less than 36 hours. Will not add to queue.')

            # check blacklist
            results = db.select('blacklist',['reason'],{'user':post['author']},'id')
            if len(results) > 0:
                errorHandler.throwError('Author blacklistet. Reason: '+results[0]['reason']+'. Will not add to queue.')

            # check previous votes for author
            results = db.select('upvotes',['created'],{'user':post['author'],'account':username,'status !':'canceled','created >':"datetime('now','-7 days')"},'created')
            if len(results) > 0:
                errorHandler.throwError('You already submitted a post of this author in the last week. Will not add to queue.')
            results = db.select('upvotes',['created'],{'user':post['author'],'status !':'canceled','created >':"datetime('now','-1 day')",'status !':'canceled'},'created')
            if len(results) > 0:
                errorHandler.throwError('Someone else already submitted a post of this author today. Will not add to queue.')

            # get queue length
            db_path = db.config.db.file
            with QueueDBHelper(db_path) as qdbh:
                queue_length = qdbh.query_queue_length()

            # check mana
            try:
                enforcer = Enforcer.from_database_user(db_path, username, chaininfo['head_block_number'])
                allowed_strength, *_ = enforcer.curate(queue_length)
                enforcer.write_to_database(db_path, username, chaininfo['head_block_number'])
            except RateLimitError as e:
                errorHandler.throwError(e.fmt(username))

            upvote_id = uuid.uuid4().hex

            post_type = 1
            if post['parent_author']:
                post_type = 2
            db.insert('upvotes',{'id':upvote_id, 'account':username, 'link': post['url'], 'user': post['author'], 'category': post['category'], 'slug': post['permlink'], 'title': post['title'], 'type': post_type, 'payout': post['cashout_time'], 'status': 'in queue', 'reward_sbd': 0, 'reward_sp': 0})

            with QueueDBHelper(db_path, read_only=False) as qdbh:
                qdbh.upsert_upvote_strength(upvote_id, allowed_strength)

        # get upvotes
        upvotes = []
        results = db.select('upvotes',['id','created','link','user','category','slug','title','type','payout','status','reward_sp'],{'account':username},'created DESC')
        for row in results:
            upvotes.append(dict(row))
        data['upvotes'] = upvotes
    api.output(data)
    return data

def get_mana(account):
    mana = account.mana.value
    stamina = account.stamina.value
    step = account.stamina.step
    return {"mana": mana,
            "stamina": {"step": step,
                        "value": stamina}}
                        
@app.route('/mana', methods=['GET', 'POST'])
def mana():
    username = request.form['username']
    userhash = request.form['userhash']
    account = request.form['account']
    try:
        requester = Account(username)
        requester.login(userhash)
        if username == account:
            return get_mana(requester)
        else:
            target = Account(account)
            with requester.admin:
                return get_mana(target)
    except CurangelError as e:
        errorHandler.throwError(e.fmt())

if __name__ == '__main__':
    app.run()
