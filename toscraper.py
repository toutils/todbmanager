#Copyright 2019
#https://github.com/toutils/todbmanager

#This file is part of todbmanager.

#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU Affero General Public License as published by
#the Free Software Foundation, either version 3 of the License, or
#(at your option) any later version.

#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU Affero General Public License for more details.

#You should have received a copy of the GNU Affero General Public License
#along with this program.  If not, see <https://www.gnu.org/licenses/>.

import traceback
from requests import Request, Session
from bs4 import BeautifulSoup
from datetime import datetime
import hashlib
import re
import json

class toscraperException(Exception):
	def __init__(self, message):
		self.message=message

def toscraper_fetch(session, to_url, url, timeout, mode='get', payload=None):
	request_url=to_url+url
	if mode=='get':
		print('toscraper_fetch: get:'+request_url)
		response=session.get(request_url, timeout=timeout)
	elif mode=='post':
		print('toscraper_fetch: post:'+request_url)
		response=session.post(request_url, timeout=timeout, data=payload)

	if response.status_code is not 200:
		raise toscraperException('Bad status code:'+str(response.status_code)+
			' from '+request_url)

	return response

	
def toscraper_login(session, to_url, email, password, timeout):
	#the login page must be pulled first to scrape "authenticity_token"
	response=toscraper_fetch(session,to_url,'login',timeout)

	soup=BeautifulSoup(response.text,'lxml')
	token=soup.find("input",attrs={"name":"authenticity_token"})['value']

	payload = {'email': email, 'password': password, 
		'authenticity_token':token }

	response=toscraper_fetch(session,to_url,'login',timeout,mode='post',
		payload=payload)

	if 'invalid username/password' in response.text:
		raise toscraperException('Invalid username/password')

	if 'logout' not in response.text:
		raise toscraperException('logout not found in response')

def toscraper_check_login(session, to_url, timeout):
	response=toscraper_fetch(session,to_url,"",timeout)
	if 'logout' in response.text:
		return True
	else:
		return False

#take a page, and check the orderby
def toscraper_check_orderby(src):
	if 'Order by edit date' in src:
		return 'creation'
	elif 'Order by creation date' in src: 
		return 'edit'
	else:
		return 'error'

def toscraper_set_orderby(session,to_url,orderby,timeout):
	#check what is currently set
	#response=toscraper_fetchget_url('reports')
	response=toscraper_fetch(session, to_url, 'reports', timeout)
	
	cur_order=toscraper_check_orderby(response.text)
	
	if cur_order==orderby:
		print('toscraper_set_orderby: requested '+orderby+' matched')
		return
	else:
		print('toscraper_set_orderby: requested '+orderby+' mismatched'
			', toggling')
		response=toscraper_fetch(session, to_url,'reg/toggle_order_by_flag',
			timeout)
		cur_order=toscraper_check_orderby(response.text)
		if cur_order!=orderby:
			raise toscraperException('tried and failed to change orderby')

def toscraper_scrape_total_pages(page):
	soup=BeautifulSoup(page,'lxml')
	
	#find the index with 'Next' and then -1
	a_pagination=soup.find_all('div',class_='pagination')[1].find_all('a')
	next_index=0
	for a in a_pagination:
		if 'Next' in a.get_text():
			break;
		else:
			next_index+=1
	
	pages=int(a_pagination[next_index-1].get_text())
	
	#for tag in a_pagination:
	#	tag.decompose()
	return pages

#append a new blocked userid
def toscraper_add_blocked_userid(userid, log_handler, filepath='block_userids'):
	f=open(filepath,'a')
	f.write(userid+'\n')
	log_handler('info','ToAPI:add_userid','added to blocked_userids:'+userid )

#scrape reports page, return list of reviews
def toscraper_scrape_reports_page(page,request_url,log_handler, user_blocklist, requester_blocklist):
	soup=BeautifulSoup(page,'lxml')
	reports=soup.find(id='reports').find_all('tr')
	reports=reports[1:len(reports)]

	cleaned_reports=[]

	for report in reports:
		try:
			c_report={}
			comment_list=[]
	
			td_list=report.find_all('td')
	
			c_report['requester_id']=td_list[0].div.a['href'].replace('/reports?id=','').strip('\n\r')
			
			#requester_name: unicode/None sqlite translates None to Null
			#some are missing requester names, and this will throw IndexError
			if len(td_list[0].div.a.contents)>0:
				c_report['requester_name']=td_list[0].div.a.contents[0].replace('/reports?id=','').strip('\n\r')
			else:
				c_report['requester_name']=None
	
			#ratings, int/None
			rating_divs=td_list[1].find_all('div')
			rating_list=[]
			rating_list.append( {'name':'fair','score':rating_divs[1].contents[0]} )
			rating_list.append( {'name':'fast','score':rating_divs[3].contents[0]} )
			rating_list.append( {'name':'pay','score':rating_divs[5].contents[0]} )
			rating_list.append( {'name':'comm','score':rating_divs[7].contents[0]} )
	
			#clean rating data
			for rating in rating_list:
				if 'no' in rating['score']:
					rating['score']=None
				else:
					#there is an ancient review (~page 14735 https://turkopticon.ucsd.edu/reports?id=A2Z6Z84FDIF2W8)
					#that throws an exception
					#<div class="smlabel">&nbsp;/&nbsp;5</div>
					#throws ValueError: invalid literal for int() with base 10: '\xa0'
					#instead of tossing the whole review, catch this and preserve everything else
					try:
						rating['score']=int(rating['score'].split('/')[0])
					except ValueError:
						log_handler('info','ToAPI:scrape_reports_page','caught value error on score field, setting to none')
						log_handler('info','ToAPI:scrape_reports_page','rating[score]='+str(rating['score']) )
						log_handler('info','ToAPI:scrape_reports_page',
							'request_url:'+request_url+' scrape exception:'+traceback.format_exc())
						rating['score']=None
						
						
			#insert into dictionary
			for rating in rating_list:
				c_report[rating['name']]=rating['score']
				
			#tosflag, True/False, sqlite translates to 1/0
			if td_list[1].find('div',{'class':'tosviol'})!=None:
				c_report['tosviol']=True
			else:
				c_report['tosviol']=False
			
			review_divs=td_list[2].find_all('div')
			
			#review, unicode
			c_report['review']=review_divs[0].get_text('\n',strip=True).strip('\n\r')
			
			#date, unicode
			#sqlite doesn't handle %b (Mar), convert to what it does
			#https://sqlite.org/lang_datefunc.html
			c_report['date']=review_divs[1].get_text().split('\n')[1]
			#c_report['date']=unicode( datetime.strptime(c_report['date'], '%b %d %Y').strftime('%m %d %Y') )
			c_report['date']=datetime.strptime(c_report['date'], '%b %d %Y').strftime('%Y-%m-%d')
			#userid, int
			c_report['user_id']=int(review_divs[1].find_all('a')[0]['href'].replace('/by/',''))
			#c_report['user_id']=int(review_divs[1].find_all('a')[0]['href'].replace('/by/',''))
			#use the comment link for the review_id, not the placeholder div
			
			#review_id, int
			#don't do this, gets edit tag for the logged in user's review
			#c_report['review_id']=int(review_div_a[4]['href'].replace('/main/add_comment/',''))
			c_report['review_id']=int(review_divs[1].find('a',text=re.compile(r'\bcomment\b'))['href'].replace('/main/add_comment/',''))

			#hash the review_id
			c_report['review_id']=hashlib.sha256(str(c_report['review_id']).encode('utf-8')).hexdigest()
			
			#notes, unicode/None
			#c_report['notes']=str(td_list[2].find("p",class_="notes")) #this will cause the string 'None' to be entered into the database, not Null
			#c_report['notes']=c_report['notes'].replace('<p class="notes">','').replace('</p>','').replace('<br/>','\n')
			c_report['notes']=str(td_list[2].find("p",class_="notes"))
			if c_report['notes']=='None':
				c_report['notes']=None
			if c_report['notes']!=None:
				c_report['notes']=c_report['notes'].replace('<p class="notes">','')
				c_report['notes']=c_report['notes'].replace('</p>','')
				c_report['notes']=c_report['notes'].replace('<br/>','\n')
				c_report['notes']=c_report['notes'].strip('\n\r')
			
			#hidden, True/False
			#this isn't implemented yet, fix this before trying to scrape a hidden reports page
			c_report['hidden']=False
			
			#look for comments
			comment_divs=td_list[2].find_all('div',class_='flag_comment')
			#print 'found:'+str(len(comment_divs))+' comment divs'
			comment_list=[]
			if len(comment_divs)>0:
				for comment in comment_divs:
					comment_dict={}
					
					#type, unicode
					comment_dict['type']=comment.find('img')['alt']
					
					#comment, unicode
					comment_dict['comment']=''.join(comment.find_all(text=True,recursive=False)).strip().strip('\n\r') #get text without children

					#flags are different than regular comments.
					#the 'posted_by' div is the next sibling(x2) of 'flag_comment', not a child
					#try to determine this
					
					#no 'posted_by' child / flag comment
					if comment.find('div',class_='posted_by')==None:
						#try to see if it's the next sibling(x2)
						if 'posted_by' in comment.next_sibling.next_sibling['class']: #next_sibling['class'] returns list
							#try for date and user id
							#date, unicode/None
							#sqlite doesn't handle %b (Mar), convert to what it does
							#https://sqlite.org/lang_datefunc.html
							comment_dict['date']=comment.next_sibling.next_sibling.find_all(text=True,recursive=False)[0].replace(u'\xa0', '').replace(u'\n','').replace(u'|','')
							comment_dict['date']=datetime.strptime(comment_dict['date'], '%b %d %Y').strftime('%Y-%m-%d')
							
							#user_id, int/None
							comment_dict['user_id']=int(comment.next_sibling.next_sibling.find('a')['href'].replace('/by/',''))

						else:
							#still nothing, log it and move on
							comment_dict['date']=None
							comment_dict['user_id']=None
							log_handler('error','ToAPI:scrape_reports_page','cant find posted_by in comment:'+str(comment))
					else: # 'posted_by' child exists / regular comment
						
						#date, unicode/None
						#sqlite doesn't handle %b (Mar), convert to what it does
						#https://sqlite.org/lang_datefunc.html
						comment_dict['date']=comment.find('div',class_='posted_by').find_all(text=True,recursive=False)[0].replace(u'\xa0', '').replace(u'\n','').replace(u'|','')
						comment_dict['date']=datetime.strptime(comment_dict['date'], '%b %d %Y').strftime('%Y-%m-%d')
						#user_id, int
						comment_dict['user_id']=int(comment.find('a')['href'].replace('/by/',''))
					
					#notes, unicode/None
					#comment_dict['notes']=comment.find('p',class_='notes').get_text() #this deletes <br> entirely
					notes=comment.p
					if notes!=None:
						for r in notes:
							if (r.string is None):
								r.string = '\n'
						comment_dict['notes']=notes.get_text().strip('\n\r')
					else:
						comment_dict['notes']=None
					#c_report['notes'] has the exact same result with a different method, test for performance

					#hash the userid
					comment_dict['user_id']=hashlib.sha256(str(comment_dict['user_id']).encode('utf-8')).hexdigest()
					
					#check for blocked userid
					if comment_dict['user_id'] in user_blocklist:
						log_handler('info','ToAPI:scrape_reports_page','blocked user:'+str(comment_dict['user_id'])+' found in comment,skipping')
					else:
						comment_list.append(comment_dict)	
				
			c_report['comments']=comment_list
			
			#generate a comment list hash, this is the only way to check for duplicates/changes
			comment_hash_str=''
			for comment in comment_list:
				comment_hash_str+=json.dumps(comment, sort_keys=True)	 
				#print "COMMENT KEY ORDER"
				#print json.dumps(comment, sort_keys=True)  
			c_report['comment_hash']=hashlib.sha256(comment_hash_str.encode('utf-8')).hexdigest()

			#hash the userid
			c_report['user_id']=hashlib.sha256(str(c_report['user_id']).encode('utf-8')).hexdigest()

			#check for [NODB] tag, to add to blocked_userids list
			if "[NODB]" in c_report['review']:
				toscraper_add_blocked_userid(c_report['user_id'], log_handler)
				user_blocklist.append(c_report['user_id'])		

			
			#check for blocked userid
			if c_report['user_id'] in user_blocklist:
				log_handler('info','ToAPI:scrape_reports_page','blocked user:'+str(c_report['user_id'])+' found in review,skipping')
			#check for blocked requesterid
			elif c_report['requester_id'] in requester_blocklist:
				log_handler('info','ToAPI:scrape_reports_page','blocked requester:'+str(c_report['requester_id'])+' found in review,skipping')
			else:
				#generate a review hash to check for changes
				c_report['review_hash']=hashlib.sha256(json.dumps(c_report, sort_keys=True).encode('utf-8')).hexdigest()
				#print "REVIEW KEY ORDER"
				#print json.dumps(c_report, sort_keys=True)

				#TESTING ONLY
				#f=open('dictdump.log', 'a')
				#f.write(json.dumps(c_report, sort_keys=True, indent=4))
				#f.write('\nComment hash str:'+comment_hash_str+'\n')
				#f.close()
				################################

				cleaned_reports.append(c_report)
				
		except(Exception):
			log_handler('error','ToAPI:scrape_reports_page','request_url:'+request_url+' scrape exception:'+traceback.format_exc())
	
	#dereference everything to avoid memory leaks
	#for tag in reports:
	#	tag.decompose()
	
	return cleaned_reports


