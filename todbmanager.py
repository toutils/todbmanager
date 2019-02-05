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

import getpass
import time
import json
from datetime import datetime
import sqlite3
import hashlib
import os
import zipfile
import mechanize
import shutil
import traceback
import io
import hashlib
#find the memory leaks
#from pympler import tracker
#from pympler import refbrowser
#import objgraph
#import inspect
#import copy


import gc
from multiprocessing import Process, Queue

#local imports
from to_api import ToAPI

#rehashing
from db_rehash import db_rehash
					  
def create_tables():
	conn=sqlite3.connect('to.db')
	cursor=conn.cursor()
	
	print 'creating reviews table if needed...'
	cursor.execute ('''create table if not exists reviews (requester_id text, requester_name text, fair integer,
			fast integer, pay integer, comm integer,review text, review_id text, date text, notes text,
			user_id text, tosviol integer, hidden integer,comment_hash text, review_hash text)''')
	
	#used by delete_userids_from_db
	print 'creating reviews indexes if needed...'
	cursor.execute ('''CREATE INDEX IF NOT EXISTS reviews_user_id_index ON reviews (user_id) ''')
	
	cursor.execute ('''CREATE INDEX IF NOT EXISTS reviews_requester_id_index ON reviews (requester_id) ''')
	cursor.execute ('''CREATE INDEX IF NOT EXISTS reviews_date_index ON reviews (requester_id) ''')
	
	#used by add_to_table
	cursor.execute ('''CREATE UNIQUE INDEX IF NOT EXISTS reviews_review_id_comment_hash_review_hash_index ON reviews (review_id, comment_hash, review_hash)''')
	
	print 'creating comments table if needed...'
	cursor.execute ('''create table if not exists comments (p_key_review integer, 
			review_id text, type text, comment text, date text, user_id text,notes text)''')
	
	print 'creating comments index if needed...'
	#used by add_to_table
	cursor.execute ('''CREATE INDEX IF NOT EXISTS comments_p_key_review_index ON comments (p_key_review) ''')
	
	cursor.execute ('''CREATE INDEX IF NOT EXISTS comments_review_id_index ON comments (review_id) ''')
	#used by delete_userids_from_db
	cursor.execute ('''CREATE INDEX IF NOT EXISTS comments_user_id_index ON comments (user_id) ''')
	
	conn.commit()
	conn.close()

#write to the log file
def log_handler(level,orig,message):
	f=open('errors.log','a')
	write_str=str(datetime.now())+':'+level+':'+orig+':'+message+'\n'
	print write_str
	f.write(write_str)
	f.close()

#check a return dict for errors, given str_originator and return_dict
#if there's an error, handle it and return True, else return the data object
#return_dict can never be 'True'
def check_error(orig,return_dict):
	if type(return_dict)!=type(dict()):
		log_handler('error','check_error:','return_dict not dict')
		return True
	elif 'status' not in return_dict:
		log_handler('error','check_error:','status not in return_dict:'+str(return_dict))
		return True
	elif return_dict['status']=='error':
		if 'message' in return_dict:
			log_handler('error','check_error:'+orig,return_dict['message'])
		else:
			log_handler('error','check_error:'+orig,'no error message')
		return True
	elif return_dict==True:
		log_handler('error','check_error:','return_dict cant be True')
		return True
	elif 'data' not in return_dict:
		log_handler('error','check_error:','data not in return_dict')
		return True
	elif return_dict['data']==True:
		log_handler('error','check_error:','return_dict["data"] cant be True')
		return True
	elif return_dict['status']=='ok':
		return return_dict['data']
	else:
		log_handler('error','check_error:','status not ok')
		return True

#get basic table stats
#return dict with stats
def get_table_status():
	conn=sqlite3.connect('to.db')
	cursor=conn.cursor()
	print 'counting reviews...'
	cursor.execute ('''SELECT Count(*) FROM reviews''')
	row=cursor.fetchone()
	total_review_rows=row[0]
	
	print 'counting comments...'
	cursor.execute ('''SELECT Count(*) FROM comments''')
	row=cursor.fetchone()
	total_comment_rows=row[0]
	
	stats_dict={}
	stats_dict['total_review_rows']=total_review_rows
	stats_dict['total_comment_rows']=total_comment_rows
	
	conn.close()
	
	return stats_dict
	
	
#add a report to a table
#check for duplicates, return added,modified,none
#takes a mod_cursor to support bulk commits, speeds up sqlite inserts
def add_to_table(report,mod_cursor,mod_conn):
	#search_conn=sqlite3.connect('to.db',timeout=60)
	search_cursor=mod_conn.cursor()
	#mod_cursor=mod_conn.cursor()
	status=None
	comments_modified=0
	
	#check if it already exists in the table
	#review_id may not be accurate, instead compare with user_id and requester_id
	#if match, update instead of add.
	
	search_cursor.execute('SELECT rowid,comment_hash,review_hash FROM reviews WHERE review_id=?',(report['review_id'],) )
	row=search_cursor.fetchone()
	
	if row==None:   #brand new review, not edited
		
		mod_cursor.execute('INSERT INTO reviews VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
			(report['requester_id'],report['requester_name'],report['fair'],report['fast'],report['pay'],
			report['comm'],report['review'],report['review_id'],report['date'],report['notes'],report['user_id'],
			report['tosviol'], report['hidden'],report['comment_hash'],report['review_hash']))
		
		#lastrowid onliy works for the last insert, not update or anything else
		p_key_review=mod_cursor.lastrowid
		if(p_key_review==None):
			print("ERROR: NEW REVIEW P_KEY_REVIEW NULL")

		for comment in report['comments']:
			mod_cursor.execute('INSERT INTO comments VALUES (?,?,?,?,?,?,?)',
				(p_key_review,report['review_id'],comment['type'],comment['comment'],comment['date'],comment['user_id'],comment['notes']))
			comments_modified+=1
			
		status='added'
	
	else: #a review was found matching review_id, check if review hash matches for changes
		if str(row[2])!=str(report['review_hash']): #the review has been changed, update
			
			mod_cursor.execute( '''UPDATE reviews SET requester_id=?, requester_name=?, fair=?, fast=?, pay=?, comm=?, review=?, 
				review_id=?,date=?,notes=?, user_id=?, tosviol=?, hidden=?, comment_hash=?, review_hash=? WHERE rowid=?''',
				(report['requester_id'],report['requester_name'],report['fair'],report['fast'],report['pay'],
				report['comm'],report['review'],report['review_id'],report['date'],report['notes'],report['user_id'],report['tosviol'],report['hidden'],
				report['comment_hash'], report['review_hash'], row[0]))

			status='replaced'
			#TESTING#####
			#print("REVIEW ROWID CHANGED:"+str(row[0]))
            #############

			#the comments may also have changed, check the comment hashes
			if report['comment_hash']!=row[1]: #comment hashes don't match
				#drop all comments for this review, and re-add
				
				#only works for insert, not update
				#p_key_review=mod_cursor.lastrowid
				p_key_review=row[0]

				if(p_key_review==None):
					#this shouldn't happen now, log if it does
					log_handler('ERROR','worker:add_to_table','comments p_key_review is null')
				
				mod_cursor.execute('DELETE FROM comments WHERE p_key_review=?',(p_key_review,) )
				for comment in report['comments']:
					mod_cursor.execute('INSERT INTO comments VALUES (?,?,?,?,?,?,?)',
					(p_key_review,report['review_id'],comment['type'],comment['comment'],comment['date'],comment['user_id'],comment['notes']))
					comments_modified+=1

	search_cursor.close()
	
	return {'status':status,'comments_modified':comments_modified,'mod_cursor':mod_cursor}
	
#given a list of userids, scan the database and retroactively delete
#reviews and comments
#userids and requesterids must be []
def delete_userids_from_db(userids, requester_ids):
	conn=sqlite3.connect('to.db',timeout=60)
	cursor=conn.cursor()
	
	print 'deleting '+str(len(userids))+' user_ids...'
	
	#delete all reviews that match one of the userids
	#don't use WHERE user_id IN, limit of 999
	
	for userid in userids:
		#cursor.execute('SELECT * FROM reviews WHERE user_id=?',(userid,) )
		cursor.execute('DELETE FROM reviews WHERE user_id=?',(userid,) )
		print 'user_id:'+str(userid)+' deleting '+str(cursor.rowcount)+' reviews'
		conn.commit()
		cursor.execute('DELETE FROM comments WHERE user_id=?',(userid,) )
		print 'user_id:'+str(userid)+' deleting '+str(cursor.rowcount)+' comments'
		conn.commit()

	print 'deleting '+str(len(requester_ids))+' requester_ids...'
	
	#delete all reviews that match one of the requesterids
	#don't use WHERE user_id IN, limit of 999
	review_ids=[]	
	for requester_id in requester_ids:
		#get the review_ids first to delete all the comments
		review_ids=[]
		cursor.execute('SELECT review_id FROM reviews WHERE requester_id=?',(requester_id,) )		
		row=cursor.fetchone()
		while(row!=None):
			review_ids.append(row[0])
			row=cursor.fetchone()
		print 'found '+str(len(review_ids))+' review_ids'

		cursor.execute('DELETE FROM reviews WHERE requester_id=?',(requester_id,) )
		print 'requester_id:'+str(requester_id)+' deleting '+str(cursor.rowcount)+' reviews'
		conn.commit()

		#delete the comments with the review_ids
		for review_id in review_ids:
			cursor.execute('DELETE FROM comments WHERE review_id=?',(review_id,) )
			print 'review_id:'+str(review_id)+' deleting '+str(cursor.rowcount)+' comments'
			conn.commit()

	conn.close()
	
#add list of cleaned reports to table
#return number of reports actually added / modified
def worker(to_api,reports_page,request_url,queue):
	#tr=tracker.SummaryTracker()

	mod_conn=sqlite3.connect('to.db',timeout=60)
	mod_cursor=mod_conn.cursor()

	#to_api blocked_userids need to be loaded everytime, changes
	#to class members are not threadsafe, if they are changed in another thread
	#the change will not be shared with the next new thread
	to_api.load_block_userids()
	to_api.load_block_requesterids()

	try:
		worker_time_scrape=time.time()
		#send the request_url to scrape_reports page so it can log the request_url if there's errors
		cleaned_reports=to_api.scrape_reports_page(reports_page,request_url)
		
		worker_time_scrape=time.time()-worker_time_scrape
		
		total_pages=check_error('scrape_to',to_api.scrape_total_pages(reports_page))

		if reports_page==True:
			print 'add_to_table:cant find total_pages'
			queue.put({'status':'error','message':'add_to_table:cant find total_pages'})
			return None

		if (len(cleaned_reports)<1):
			
			print 'add_to_table:bad cleaned reports'
			queue.put({'status':'error','message':'add_to_table:bad cleaned reports'})
			return None
		
		added=0
		replaced=0
		comments_modified=0
		worker_time_db=time.time()
	
		for report in cleaned_reports:	
			
			#send the mod_cursor to take all the inserts, commit the mod_cursor after the loop
			response=add_to_table(report,mod_cursor,mod_conn)
			mod_cursor=response['mod_cursor']
			
			if response['status']=='added':
				added+=1
			elif response['status']=='replaced':
				replaced+=1
			comments_modified+=response['comments_modified']
		
		mod_conn.commit() #commit only after all the cleaned reports are in the cursor
		mod_conn.close()
		worker_time_db=time.time()-worker_time_db
			
		queue.put( {'status':'ok','data':{'added':added,'replaced':replaced,'total':len(cleaned_reports),'request_url':request_url,'total_pages':total_pages,
				'comments_modified':comments_modified,'worker_time_scrape':worker_time_scrape,'worker_time_db':worker_time_db} } )
		
		#avoid memory leaks
		queue.close()
		queue.join_thread()
		gc.collect(2)
		
	except KeyboardInterrupt:
		mod_conn.close()

def drop_to_table():
	conn=sqlite3.connect('to.db')
	cursor=conn.cursor()
	cursor.execute('DROP TABLE reviews')
	cursor.execute('DROP TABLE comments')
	conn.commit()
	conn.close()
	create_tables()
	
	
#full scraping function with logged in br
def scrape_to(to_api,page_start, page_end, rate_limit,auto_update):
	log_handler('info','scrape_to','scrape started')
	#tr=tracker.SummaryTracker() #find memory leaks
	
	reports_page=check_error('scrape_to',to_api.get_url('reports'))
	if reports_page==True:
		return None
	
	total_pages=check_error('scrape_to',to_api.scrape_total_pages(reports_page))
	if reports_page==True:
		return None
	
	if page_start>total_pages:
		page_start=total_pages
		
	if page_end>total_pages:
		page_end=total_pages
				
	if page_end==0:
		update_page_end=True
		print 'scrape_to:'+'auto updating page_end'
	else:
		update_page_end=False
		
	if (auto_update):
		print 'scrape_to:auto update enabled'
		print 'scarpe_to:setting orderby to edit'
		response=to_api.set_orderby('edit')
		if check_error('scrape_to',response)==True:
			print 'ERROR IN CHECK_ERROR AUTO'
			return
	else:
		print 'scrape_to:auto update disabled'
		print 'scrape:to:setting ordby to creation'
		response=to_api.set_orderby('creation')
		if check_error('scrape_to',response)==True:
			print 'ERROR IN CHECK_ERROR NOAUTO'
			return
	
	if page_end>total_pages or page_end==0:
		page_end=total_pages
	
	print 'scraping pages:'+str(page_start)+'-'+str(page_end)
	current_page=page_start
	total_added=0
	total_replaced=0
	total_comments_modified=0
	total_processed=0
	scrape_process=None
	auto_update_break=False
	process_wait_time=0
	rate_limit_wait_time=0
	
	start_time=time.time()
	try:
		queue=Queue(1)
		
		while(current_page<=page_end):
			
			rate_limit_wait_time=rate_limit-(time.time()-start_time)
			if rate_limit_wait_time>0:
				print "rate limit,waiting:"+str(rate_limit_wait_time)
				time.sleep(rate_limit_wait_time)
			
			request_url='reports?page='+str(current_page)
			
			start_time=time.time()
			print 'requesting:'+request_url
			reports_page=check_error('scrape_to',to_api.get_url(request_url))
			request_time=time.time()-start_time
			
			if reports_page==True:
				print 'scrape_to:to_api.get_url failed, stopping update'
				break

			#wait for scrape process to finish
			if scrape_process!=None:
				
				print 'waiting for worker process to finish...'

				process_wait_time=time.time()
				process_stats=check_error('scrape_to',queue.get())
				
				scrape_process.join()
				process_wait_time=time.time()-process_wait_time
				
				if process_stats!=True:
					#no errors, check_error should handle logging if there was
					print ('----worker added:'+str(process_stats['added'])+' replaced:'+str(process_stats['replaced'])+' /'+
						   str(process_stats['total'])+' comments_modified:'+str(process_stats['comments_modified'])+' from:'+process_stats['request_url'])
					print '----worker time: scrape:'+str(process_stats['worker_time_scrape'])+' db:'+str(process_stats['worker_time_db'])
					total_added+=process_stats['added']
					total_replaced+=process_stats['replaced']
					total_processed+=process_stats['total']
					total_comments_modified+=process_stats['comments_modified']
					
					#if auto_update, update page_end with total pages
					#break the update loop if added+replaced=0
						
					if (auto_update):
						if (process_stats['added']+process_stats['replaced'])==0:
							#no new data, stop updating
							print 'scape_to:no new data found, stopping update'
							scrape_process.join()
							scrape_process=None
							break
					if (update_page_end):
						if page_end!=process_stats['total_pages']:
							print 'scrape_to:new total_pages found:'+(str(process_stats['total_pages']))
							page_end=process_stats['total_pages']
							
					if rate_limit_wait_time<0: #this will happen when rate limit not exceeded
						total_wait_time=request_time+process_wait_time
					else:
						total_wait_time=request_time+rate_limit_wait_time+process_wait_time
							
					print 'time total:'+str(total_wait_time)+'s request:'+str(request_time)+'s rate_limit:'+str(rate_limit_wait_time)+'s process_wait:'+str(process_wait_time)
					print 'pages remaining:'+str(page_end-current_page)+' eta:'+str((page_end-current_page)*(total_wait_time))+'s'	
		
			#run garbage collector before starting new process
			gc.collect(2)
			
			print 'launching process for:'+request_url
			scrape_process=Process(target=worker,args=(to_api,reports_page,request_url,queue))
			scrape_process.start()
			current_page+=1

	#wait for scrape process to finish
		if scrape_process!=None:
			print 'waiting for worker process to finish...'
			scrape_process.join()
			process_stats=check_error('scrape_to',queue.get())
			if process_stats!=True:
				print ('----worker added:'+str(process_stats['added'])+' replaced:'+str(process_stats['replaced'])+' /'+
						str(process_stats['total'])+' comments_modified:'+str(process_stats['comments_modified'])+' from:'+process_stats['request_url'])
				total_added+=process_stats['added']
				total_replaced+=process_stats['replaced']
				total_processed+=process_stats['total']
				total_comments_modified+=process_stats['comments_modified']
			
	except KeyboardInterrupt:
		log_handler('info','scrape_to','keyboardinterrupt stopped scrape')
		print 'Interrupt detected'
			
	print 'Total Added:'+str(total_added)+' Replaced:'+str(total_replaced)+' Processed:'+str(total_processed)
	print 'Comments Modified:'+str(total_comments_modified)

def save_scrape_reports_to_file(reports,filename):
	f=open(filename,'w')
	reports=json.dumps(reports)
	f.write(reports)
	f.close()
	return reports

def load_scrape_reports_from_file(filename):
	f=open(filename,'r')
	reports=json.loads(f.read())
	f.close()
	return reports	

#run a test page through ToAPI.scrape_reports_page and save the result
def save_test_page_known_good(filename):
	test_to_api=ToAPI(log_handler)
	test_page=io.open(filename,'r', encoding="utf-8").read()
	reports=test_to_api.scrape_reports_page(test_page,"Test")
	save_scrape_reports_to_file(reports,filename+'.json')
	print('test page known good saved')
	
#test ToAPI.scrape_reports_page against known goods
#if this test fails, there's a change in scrape_reports_page that
#will cause a database change
def test_scrape_reports_page():
	
	test_to_api=ToAPI(log_handler,block_ids=False)
	test_page=io.open('test_pages/report_w_m_comment_m_review_edit.html','r', encoding="utf-8").read()
	
	reports=test_to_api.scrape_reports_page(test_page,"Test")
	known_good_reports=load_scrape_reports_from_file('test_pages/report_w_m_comment_m_review_edit.html.json')

	if reports==known_good_reports:
		return {'status':'pass'}
	else:
		#figure out what's changed
		#if this throws an exception then the keys have changed
		fail_list=[]
		count=0
		while(count<=len(reports)):
			report_fail_list=[]
			try:
				for key,value in known_good_reports[count].iteritems():
					if reports[count][key]!=value:
						report_fail_list.append( ['value_fail',key, value, reports[count][key]] )
					if type(reports[count][key])!=type(value):
						report_fail_list.append( ['type_fail',key, str(type(value)), str(type(reports[count][key]))] )
			except:
				report_fail_list.append( ['key_fail'] )
			fail_list.append(report_fail_list)
			count+=1
		return {'status':'fail','fail_list':fail_list}


#run all the tests, return true/false if pass/fail
def run_tests():
	pass_status=True
	result=test_scrape_reports_page()
	if result['status']=='pass':
		print 'scrape_reports_page:PASS'
	else:
		print 'scrape_reports_page:FAIL'
		print str(result['fail_list'][0])
		pass_status=False
		
	return pass_status
		
#download the to_database and save to file, unzip it, and cleanup
#this will delete/overwrite an existing to.db.zip if it exists
def download_database(db_url):
	#use a seperate browser
	br=mechanize.Browser()
	try:
		#if to.db.zip is already there, delete it
		if os.path.isfile('to.db.zip')==True:
			os.remove('to.db.zip')
			
		print 'downloading database...'
		br.retrieve(db_url,'to.db.zip')
		
		print 'unzipping database...'
		zip_file=zipfile.ZipFile('to.db.zip','r')
		zip_file.extractall('') #extract to current directory
		zip_file.close()
		#cleanup
		os.remove('to.db.zip')
		
		if os.path.isfile('to.db')==False:
			#this should track and cleanup whatever just got unzipped
			return {'status':'error','message':'to.db not in zip'}

		return {'status':'ok','data':None}
		
	except:
		return {'status':'error', 'message':'exception:'+traceback.format_exc()}

#export the database without indexes, optionally strip ids
def export_database(export_filepath, strip_ids):
	#abort if export_filepath already exists

	if os.path.isfile(export_filepath)==True:
		log_handler('error','export_database',export_filepath+' already exists, aborting')
		return

	print 'copying database to '+export_filepath+' ...'
	try:
		shutil.copyfile('to.db',export_filepath)
	except Exception, e:
		self.log_handler('error','export:database','shutil exception:'+traceback.format_exc())

	#read the new database and drop the indexes if they exist
	export_conn=sqlite3.connect(export_filepath)
	export_cursor=export_conn.cursor()

	print 'dropping indexes...'
	export_cursor.execute('SELECT name FROM sqlite_master WHERE type == "index"')
	row=export_cursor.fetchone()
	
	index_list=[]
	while(row!=None):
		print 'found:'+str(row[0])
		index_list.append(row[0])
		#print 'dropping '+str(row[0])+'...'
		#export_cursor.execute('DROP INDEX '+str(row[0]))
		row=export_cursor.fetchone()
	for i in index_list:
		print 'dropping '+str(i)+'...'
		export_cursor.execute('DROP INDEX '+str(i))

	export_conn.commit()

	print 'setting review_hash to null...'
	export_cursor.execute('UPDATE reviews SET review_hash=null;')
	export_conn.commit()
	print 'setting comment_hash to null...'
	export_cursor.execute('UPDATE reviews SET comment_hash=null;')
	export_conn.commit()

	print 'vacuuming...'
	export_cursor.execute('VACUUM')
	export_conn.commit()
	export_conn.close()
	print('export complete')
	
		
def main():
	to_api=ToAPI(log_handler)
	
	#disable database download option
	#db_url=
	'''
	print 'checking for database...'
	
	if os.path.isfile('to.db')==False:
		sel=raw_input('to.db not found, download it? (y)/n:')
		if sel=='y' or sel=='':
			check_error('main',download_database(db_url))
		else:
			create_tables() #this will do nothing if the database exists or just got downloaded
	else:
		print 'database found,checking tables'
		create_tables()
	'''
	#create tables will create tables and indexes if needed
	create_tables()
	#rehash the database if needed
	print('recreating hashes if needed...')
	db_rehash('to.db', TESTING=False, null_only=True)
	
	while(1==1):
		print '===TO Database Manager==='
		print '1: Update Database'
		print '2: Database Stats'
		print '3: Delete Blocked Ids from Database'
		print '4: Delete Database'
		print '5: Download Database (Broken)'
		print '6: Run Tests'
		print '7: Export Database'
		print 'q: Quit'
		sel=raw_input("select:")
		if sel=='1':
			print 'Update Database'
			print 'running self test...'
			if run_tests():
				print 'checking if logged in...'
				while(to_api.check_login()!=True):
					print 'not logged in'
					email=raw_input("Email:")
					password=getpass.getpass("Pass:")
					print "sending login request..."
			
					logged_out=check_error('main',to_api.login(email,password))
					if logged_out==None:
						print 'login success!'
			
				print 'config: enter for (default)'
				print 'auto-update: will stop update when no new data on a page'
			
				auto_update=None
				while(auto_update==None):
					auto_update=raw_input('auto-update (y)/n:')
					if auto_update=='y':
						auto_update=True
					elif auto_update=='n':
						auto_update=False
					elif auto_update=='':
						auto_update=True
					else:
						auto_update=None
						print 'invalid, please enter "y" for yes, "n" for no or press enter for default'

				page_start=0
				while (page_start<1):
					page_start=raw_input('page start(1):')
					if page_start=='':
						page_start=1
					else:
						try:
							page_start=int(page_start)
							if page_start<1:
								print 'invalid, please enter an integer larger than 0, or press enter for default'
						except:
							print 'invalid, please enter an integer larger than 0, or press enter for default'
		
				page_end=-1
				while (page_end<=-1):
					print 'page end:0 = all pages (default)'
					page_end=raw_input('page end(0):')
					if page_end=='':
						page_end=0
					else:
						try:
							page_end=int(page_end)
							if page_end<0:
								print 'invalid, please enter 0 or a positive integer, or press enter for default'
						except:
							print 'invalid, please enter 0 or a positive integer, or press enter for default'
					
				rate_limit=-1
				while(rate_limit<=0):
					rate_limit=raw_input('rate limit(2.0) in seconds:')
					if rate_limit=='':
						rate_limit=2.0
					else:
						try:
							rate_limit=float(rate_limit)
							if rate_limit<0:
								print 'invalid, please enter a positive number, or press enter for default'
						except:
							print 'invalid, please enter a positive number, or press enter for default'
			
				scrape_to(to_api,page_start,page_end,rate_limit,auto_update)
			else:
				print 'self tests failed: unable to continue'
			
		elif sel=='2':
			print 'Database Stats'
			stats_dict=get_table_status()
			print 'Total Reviews:'+str(stats_dict['total_review_rows'])
			print 'Total Comments:'+str(stats_dict['total_comment_rows'])
		
		elif sel=='3':
			print 'Remove Blocked Ids from Database'
			print 'This will retroactively delete reviews and comments by user and requester ids'
			print 'in the blocked_userids and blocked_requesterids file, it might take a while.'
			confirm=raw_input('proceed( y/(n) ):')
			if confirm=='y':
				#this is not the way
				to_api.load_block_userids()
				to_api.load_block_requesterids()
				delete_userids_from_db(to_api.blocked_userids, to_api.blocked_requesterids)
			
		elif sel=='4':
			print "Delete Database"
			print "WARNING:This delete all tables, and re-create them."
			print "All data will be lost!"
			confirm=raw_input("type DELETE and to confirm, otherwise press enter to go back:")
			if confirm=="DELETE":
				print 'deleting database...'
				drop_to_table()
				print "tables dropped and re-created"
		
		elif sel=='5':
			#disable database download
			'''
			print 'Download Database'
			print 'WARNING:This will delete this existing database, and download a new one'
			print 'The existing database will be lost!'
			confirm=raw_input("type DOWNLOAD to confirm, otherwise press enter to go back:")
			if confirm=="DOWNLOAD":
				if os.path.isfile('to.db')==True:
					os.remove('to.db')
				if (check_error('main',download_database(db_url)))!=True:
					stats_dict=get_table_status()
					print 'Total Reviews:'+str(stats_dict['total_review_rows'])
					print 'Total Comments:'+str(stats_dict['total_comment_rows'])
			'''
			print 'Download database not implemented in this version'
				
		elif sel=='6':
			print 'Run Tests'
			run_tests()

		elif sel=='7':
			print 'Export Database'
			print 'Save a database for export, drops indexes and optionally deletes user_ids'
			export_filepath=raw_input("export filepath:")
			#print 'Strip IDs? (if IDs are stripped, you cannot update the database with todbmanager)'
			#choice=None
			#while(choice==None):
			#	choice=raw_input('strip ids? y/(n):')
			#	if choice=='y':
			#		strip_ids=True
			#	elif choice=='n' or choice=='':
			#		strip_ids=False
			#	else:
			#		print 'invalid, please enter "y" for yes, "n" for no or press enter for default'
			#		choice=None
			export_database(export_filepath, False)
			
			
			
			
		elif sel=='q':
			return None
		
if __name__ == '__main__':
	main()
	#save_test_page_known_good('test_pages/report_w_m_comment_m_review_edit.html')
