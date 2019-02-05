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


# all TO network interaction goes here
# all TO scraping functionality also goes here
import mechanize
import cookielib
import traceback
from bs4 import BeautifulSoup
import hashlib
import json
import re
from datetime import datetime

#MODIFYING CLASS MEMBERS IS NOT THREAD SAFE
#blocked_userids need to be loaded everytime they are checked, there's a better way to do this
class ToAPI:
	br=None
	blocked_userids=[]
	blocked_requesterids=[]
	to_url='https://turkopticon.ucsd.edu/'
	def __init__(self,log_handler,block_ids=True):
		self.log_handler=log_handler
		if block_ids==True:
			self.load_block_userids('block_userids')
		
	
	#userids are now sha256 of userid
	def load_block_userids(self,filepath='block_userids'):
		#load block userids from file
		try:
			f=open(filepath,'r')
			userids=f.read()
			userids=userids.split('\n')
			cleaned_userids=[]
			for user in userids:
				try:
					if user!='' and user!='\n': #ignore blanks
						cleaned_userids.append(user)
					#print 'added:'+str(user)
				except Exception,e:
					self.log_handler('error','ToAPI:load_block_userids','cant add:'+str(user)+':'+'exception:'+traceback.format_exc())
			self.blocked_userids=cleaned_userids
		except:
			self.log_handler('error','ToAPI:load_block_userids','error loading userids:exception:'+traceback.format_exc())

	#userids are now sha256 of userid
	def load_block_requesterids(self,filepath='block_requesterids'):
		#load block userids from file
		try:
			f=open(filepath,'r')
			requesterids=f.read()
			requesterids=requesterids.split('\n')
			cleaned_requesterids=[]
			for r in requesterids:
				try:
					if r!='' and r!='\n': #ignore blanks
						cleaned_requesterids.append(r)
					#print 'added:'+str(user)
				except Exception,e:
					self.log_handler('error','ToAPI:load_block_requesterids','cant add:'+str(r)+':'+'exception:'+traceback.format_exc())
			self.blocked_requesterids=cleaned_requesterids
		except:
			self.log_handler('error','ToAPI:load_block_requesterids','error loading requesterids:exception:'+traceback.format_exc())

	#add a new userid to block and append it to the file
	def add_blocked_userid(self, userid, filepath='block_userids'):
		if userid not in self.blocked_userids:
			self.blocked_userids.append(userid)
			f=open(filepath,'a')
			f.write(userid+'\n')
			self.log_handler('info','ToAPI:add_userid','added to blocked_userids:'+userid )
	
	#take a page, and check the orderby
	def check_orderby(self,src):
		if 'Order by edit date' in src:
			return 'creation'
		elif 'Order by creation date' in src: 
			return 'edit'
		else:
			return 'error'
	
	#set the orderby, must have authenticated browser already
	#orderby = edit,creation
	def set_orderby(self,orderby):
		#check what is currently set
		response=self.get_url('reports')
		if response['status']!='ok':
			return {'status':'error','message':'set_orderby:'+response['message']}
		cur_order=self.check_orderby(response['data'])
		
		if cur_order==orderby:
			return {'status':'ok','data':cur_order}
		else:
			response=self.get_url('reg/toggle_order_by_flag')
			if response['status']!='ok':
				return {'status':'error','message':'set_orderby:'+response['message']}
			else:
				cur_order=self.check_orderby(response['data'])
				if cur_order!=orderby:
					return {'status':'error','message':'set_orderby:cur_order still not set:cur_order:'+cur_order}
				else:
					return {'status':'ok','data':cur_order}
					
				
				
	#login,given str_email,str_password, return 'status':'ok' or 'status':'error','message':str_error
	#set self.br to logged in browser if good login
	def login(self,email, password):
		br=mechanize.Browser()
		cookiejar = cookielib.LWPCookieJar()
		br.set_cookiejar( cookiejar )
		br.set_handle_equiv( True ) 
		br.set_handle_gzip( True ) 
		br.set_handle_redirect( True ) 
		br.set_handle_referer( True ) 
		br.set_handle_robots( False ) 

		#br.addheaders = [ ( 'User-agent', 'Mozilla/5.0 (X11; U; Linux i686; en-US; rv:1.9.0.1) Gecko/2008071615 Fedora/3.0.1-1.fc9 Firefox/3.0.1' ) ]
	
		br.open(self.to_url+'login')
		br.select_form(nr=0)
		br['email']=email
		br['password']=password
		response=br.submit()
		src=response.read()
	
		if 'invalid username/password' in src:
			return {'status':'error','message':'ToAPI:login:bad username/password'}
	
		elif 'logout' not in src:
			return {'status':'error','message':'ToAPI:login:logout not found'}
	
		else:
			self.br=br
			return {'status':'ok','data':None}
	
		
	#check if the browser is already logged in
	#return true/false
	def check_login(self):
		if self.br==None:
			return False
		response=self.br.open(self.to_url).read() #this should be using self.get_url
		
		if 'logout' in response:
			return True
		else:
			return False
		
			
	#get a url, return 'status':'ok','data':str_source or 'status':'error','message':str_error
	def get_url(self,url):
		request_url=self.to_url+url
		max_retry_count=40
		count=0
		src=''
		while(count<=max_retry_count):
			try:
				response=self.br.open(request_url,timeout=10)
				src=response.read()
				response.close()
				break
			except Exception,e:
				self.log_handler('error','ToAPI:get_url','url:'+url+' count:'+str(count)+' mechanize_error:'+traceback.format_exc())
			count+=1
			
		#this was a cause of memory blowing up
		#delete the history
		self.br.clear_history()
		
		if 'logout' not in src:
			return { 'status':'error','message':'get_to_url:br not logged in' }
		else:
			return { 'status':'ok','data':src }
		
	#given str_reports_page, return 'status':'ok','data':int_total_pages or 'status':'error','message':str_error
	def scrape_total_pages(self,page):
		#page=get_to_url(br,'reports')
	
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
		
		for tag in a_pagination:
			tag.decompose()

		return {'status':'ok','data':pages }
		
		
	#scrape reports page, return list of reviews
	def scrape_reports_page(self,page,request_url):
		soup=BeautifulSoup(page,'lxml')
		reports=soup.find(id='reports').find_all('tr')
		reports=reports[1:len(reports)]
	
		cleaned_reports=[]
	
		for report in reports:
			try:
				c_report={}
				comment_list=[]
		
				td_list=report.find_all('td')
		
				#requester_id: unicode
				c_report['requester_id']=unicode(td_list[0].div.a['href'].replace('/reports?id=','')).strip('\n\r')
				
				#requester_name: unicode/None sqlite translates None to Null
				#some are missing requester names, and this will throw IndexError
				if len(td_list[0].div.a.contents)>0:
					c_report['requester_name']=unicode(td_list[0].div.a.contents[0].replace('/reports?id=','')).strip('\n\r')
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
						rating['score']=int(rating['score'].encode('ascii',errors='ignore').split('/')[0])
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
				c_report['review']=unicode(review_divs[0].get_text('\n',strip=True)).strip('\n\r')
				
				#date, unicode
				#sqlite doesn't handle %b (Mar), convert to what it does
				#https://sqlite.org/lang_datefunc.html
				c_report['date']=review_divs[1].get_text().split('\n')[1]
				#c_report['date']=unicode( datetime.strptime(c_report['date'], '%b %d %Y').strftime('%m %d %Y') )
				c_report['date']=unicode( datetime.strptime(c_report['date'], '%b %d %Y').strftime('%Y-%m-%d'))
				#userid, int
				c_report['user_id']=int(review_divs[1].find_all('a')[0]['href'].replace('/by/',''))
				#c_report['user_id']=int(review_divs[1].find_all('a')[0]['href'].replace('/by/',''))
				#use the comment link for the review_id, not the placeholder div
				
				#review_id, int
				#don't do this, gets edit tag for the logged in user's review
				#c_report['review_id']=int(review_div_a[4]['href'].replace('/main/add_comment/',''))
				c_report['review_id']=int(review_divs[1].find('a',text=re.compile(r'\bcomment\b'))['href'].replace('/main/add_comment/',''))

				#hash the review_id
				c_report['review_id']=unicode(hashlib.sha256(str(c_report['review_id'])).hexdigest())
				
				#notes, unicode/None
				#c_report['notes']=str(td_list[2].find("p",class_="notes")) #this will cause the string 'None' to be entered into the database, not Null
				#c_report['notes']=c_report['notes'].replace('<p class="notes">','').replace('</p>','').replace('<br/>','\n')
				c_report['notes']=td_list[2].find("p",class_="notes")
				if c_report['notes']!=None:
					c_report['notes']=unicode(c_report['notes']).replace('<p class="notes">','').replace('</p>','').replace('<br/>','\n').strip('\n\r')
				
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
						comment_dict['type']=unicode(comment.find('img')['alt'])
						
						#comment, unicode
						comment_dict['comment']=unicode(''.join(comment.find_all(text=True,recursive=False)).strip()).strip('\n\r') #get text without children

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
								comment_dict['date']=unicode( datetime.strptime(comment_dict['date'], '%b %d %Y').strftime('%Y-%m-%d'))
								
								#user_id, int/None
								comment_dict['user_id']=int(comment.next_sibling.next_sibling.find('a')['href'].replace('/by/',''))

							else:
								#still nothing, log it and move on
								comment_dict['date']=None
								comment_dict['user_id']=None
								self.log_handler('error','ToAPI:scrape_reports_page','cant find posted_by in comment:'+str(comment))
						else: # 'posted_by' child exists / regular comment
							
							#date, unicode/None
							#sqlite doesn't handle %b (Mar), convert to what it does
							#https://sqlite.org/lang_datefunc.html
							comment_dict['date']=unicode(comment.find('div',class_='posted_by').find_all(text=True,recursive=False)[0]).replace(u'\xa0', '').replace(u'\n','').replace(u'|','')
							comment_dict['date']=unicode( datetime.strptime(comment_dict['date'], '%b %d %Y').strftime('%Y-%m-%d'))
							#user_id, int
							comment_dict['user_id']=int(comment.find('a')['href'].replace('/by/',''))
						
						#notes, unicode/None
						#comment_dict['notes']=comment.find('p',class_='notes').get_text() #this deletes <br> entirely
						notes=comment.p
						if notes!=None:
							for r in notes:
								if (r.string is None):
									r.string = '\n'
							comment_dict['notes']=unicode(notes.get_text()).strip('\n\r')
						else:
							comment_dict['notes']=None
						#c_report['notes'] has the exact same result with a different method, test for performance

						#hash the userid
						comment_dict['user_id']=unicode(hashlib.sha256(str(comment_dict['user_id'])).hexdigest())
						
						#check for blocked userid
						if comment_dict['user_id'] in self.blocked_userids:
							self.log_handler('info','ToAPI:scrape_reports_page','blocked user:'+str(comment_dict['user_id'])+' found in comment,skipping')
						else:
							comment_list.append(comment_dict)	
					
				c_report['comments']=comment_list
				
				#generate a comment list hash, this is the only way to check for duplicates/changes
				comment_hash_str=''
				for comment in comment_list:
					comment_hash_str+=json.dumps(comment, sort_keys=True)	 
					#print "COMMENT KEY ORDER"
					#print json.dumps(comment, sort_keys=True)  
				c_report['comment_hash']=unicode(hashlib.sha256(comment_hash_str).hexdigest())

				#hash the userid
				c_report['user_id']=unicode(hashlib.sha256(str(c_report['user_id'])).hexdigest())

				#check for [NODB] tag, to add to blocked_userids list
				if "[NODB]" in c_report['review']:
					self.add_blocked_userid(c_report['user_id'])
								
				#check for blocked userid
				if c_report['user_id'] in self.blocked_userids:
					self.log_handler('info','ToAPI:scrape_reports_page','blocked user:'+str(c_report['user_id'])+' found in review,skipping')
				#check for blocked requesterid
				elif c_report['requester_id'] in self.blocked_requesterids:
					self.log_handler('info','ToAPI:scrape_reports_page','blocked requester:'+str(c_report['requester_id'])+' found in review,skipping')
				else:
					#generate a review hash to check for changes
					c_report['review_hash']=unicode(hashlib.sha256(json.dumps(c_report, sort_keys=True)).hexdigest())
					#print "REVIEW KEY ORDER"
					#print json.dumps(c_report, sort_keys=True)

					#TESTING ONLY
					#f=open('dictdump.log', 'a')
					#f.write(json.dumps(c_report, sort_keys=True, indent=4))
					#f.write('\nComment hash str:'+comment_hash_str+'\n')
					#f.close()
					################################

					cleaned_reports.append(c_report)
					
			except Exception,e:
				self.log_handler('error','ToAPI:scrape_reports_page','request_url:'+request_url+' scrape exception:'+traceback.format_exc())
		
		#dereference everything to avoid memory leaks
		for tag in reports:
			tag.decompose()
		
		return cleaned_reports
	