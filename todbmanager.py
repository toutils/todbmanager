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

import argparse
import traceback
from datetime import datetime
from getpass import getpass
from requests import Request, Session
import time
import io
import json

#to set requests retry behavior
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry


from todb import *
from toscraper import *

class todbmanagerException(Exception):
	def __init__(self, message):
		self.message=message

to_url='https://turkopticon.ucsd.edu/'

#write to the log file
def log_handler(level,orig,message):
	f=open('errors.log','a')
	write_str=str(datetime.now())+':'+level+':'+orig+':'+message
	print (write_str)
	write_str+='\n'
	f.write(write_str)
	f.close()

def load_blocklist(filepath):
	f=open(filepath,'r')
	blocked_ids=f.read().split('\n')
	cleaned_list=[]
	for r in blocked_ids:
		if r!='' and r!='\n': #ignore blanks
			cleaned_list.append(r)
	return cleaned_list

def scrape_to(session,dbpath,to_url,page_start,page_end,rate_limit,dontstop,
		timeout, user_blocklist, requester_blocklist):
	log_handler('info','scrape_to','scrape started '
		'page_start:'+str(page_start)+' page_end:'+str(page_end)+' rate_limit:'+
		str(rate_limit)+' dontstop:'+str(dontstop))

	try:
		response=toscraper_fetch(session, to_url, 'reports', timeout)
	except(Exception):
		log_handler('error','scrape_to','fetch exception url:reports')
		log_handler('error','scrape_to',traceback.format_exc())
		return
		
	try:
		total_pages=toscraper_scrape_total_pages(response.text)
	except(Exception):
		log_handler('error','scrape_to','unable to scrape total_pages')
		log_handler('error','scrape_to','url:reports')
		log_handler('error','scrape_to',traceback.format_exc())
		try:
			f=open('error_last_page.html','w')
			f.write(response.text)
			f.close()
			log_handler('error','scrape_to','last page saved to '
				'error_last_page.html')
		except(Exception):
			log_handler('error','scrape_to','unable to save response')
			log_handler('error','scrape_to',traceback.format_exc())
		return
			

	print('scrape_to:total pages:'+str(total_pages))

	if page_start>total_pages:
		page_start=total_pages
	if page_end>total_pages:
		page_end=total_pages
	if page_end==0:
		update_page_end=True
		print('scrape_to:auto updating page_end')
		page_end=total_pages
	else:
		update_page_end=False

	print('scraping pages:'+str(page_start)+'-'+str(page_end))
	current_page=page_start
	total_added=0
	total_replaced=0
	total_comments_modified=0
	total_processed=0
	auto_update_break=False
	#process_wait_time=0
	rate_limit_wait_time=0
	time_start=time.time()
	time_last_request=time.time()

	while(current_page<=page_end):
		time_start=time.time()
		rate_limit_wait_time=rate_limit-(time.time()-time_last_request)
		if rate_limit_wait_time>0:
			print("rate limit,waiting:%.4fs" % (rate_limit_wait_time,))
			time.sleep(rate_limit_wait_time)

		request_url='reports?page='+str(current_page)
		time_last_request=time.time()
		try:
			response=toscraper_fetch(session, to_url, request_url, timeout)
		except(Exception):
			log_handler('error','scrape_to','fetch exception url:'+request_url)
			log_handler('error','scrape_to',traceback.format_exc())
			return

		time_request=time.time()-time_last_request
		time_scrape=time.time()
		try:
			cleaned_reports=toscraper_scrape_reports_page(response.text,request_url,
				log_handler,user_blocklist, requester_blocklist)
			total_pages=toscraper_scrape_total_pages(response.text)
		except(Exception):
			log_handler('error','scrape_to','scraping error')
			log_handler('error','scrape_to','url:'+request_url)
			log_handler('error','scrape_to',traceback.format_exc())
			try:
				f=open('error_last_page.html','w')
				f.write(response.text)
				f.close()
				log_handler('error','scrape_to','last page saved to '
					'error_last_page.html')
			except(Exception):
				log_handler('error','scrape_to','unable to save response')
				log_handler('error','scrape_to',traceback.format_exc())
			return

		time_scrape=time.time()-time_scrape

		added=0
		replaced=0
		comments_modified=0

		time_db=time.time()
		for report in cleaned_reports:
			try:
				db_result=todb_add_to_table(dbpath,report,log_handler)
			except(Exception):
				log_handler('error','scrape_to','database error')
				log_handler('error','scrape_to','url:'+request_url)
				log_handler('error','scrape_to',traceback.format_exc())
				try:
					f=open('error_reports.json','w')
					f.write(json.dumps(reports))
					f.close()
					log_handler('error','scrape_to','reports saved to '
					'error_reports.json')
				except(Exception):
					log_handler('error','scrape_to','unable to save reports')
					log_handler('error','scrape_to',traceback.format_exc())
				try:
					f=open('error_last_page.html','w')
					f.write(response.text)
					f.close()
					log_handler('error','scrape_to','last page saved to '
						'error_last_page.html')
				except(Exception):
					log_handler('error','scrape_to','unable to save response')
					log_handler('error','scrape_to',traceback.format_exc())
				return

			if db_result['status']=='added':
				added+=1
			elif db_result['status']=='replaced':
				replaced+=1
			comments_modified+=db_result['comments_modified']

		time_db=time.time()-time_db

		print ('----added:'+str(added)+' replaced:'+str(replaced)+' /'+
			str(len(cleaned_reports))+' comments_modified:'+
			str(comments_modified)+' from:'+request_url)
		print('----time: scrape:%.4fs db:%.4fs' % (time_scrape,time_db))

		total_added+=added
		total_replaced+=replaced
		total_processed+=len(cleaned_reports)
		total_comments_modified+=comments_modified

		#if auto_update, update page_end with total pages
		#break the update loop if added+replaced=0
		if not dontstop:
			if (added+replaced)==0:
				#no new data, stop updating
				log_handler('info','scrape_to',
					'no new data found, stopping update')
				break
		if (update_page_end):
			if page_end!=total_pages:
				log_handler('info','scrape_to',
				'new total_pages found:'+str(total_pages))
				page_end=total_pages

		total_wait_time=time.time()-time_start

		print('----time: total:%.4fs request:%.4fs rate_limit:%.4fs' % (
			total_wait_time, time_request, rate_limit_wait_time))
		print('----pages remaining:%i eta:%.4fs' %
			(page_end-current_page,(page_end-current_page)*total_wait_time))
		
		current_page+=1
		
	log_handler('info','scrape_to',
	'Total Reviews Added:'+str(total_added)+' Replaced:'+
	str(total_replaced)+' Processed:'+str(total_processed)+
	' Comments Modified:'+str(total_comments_modified) )
			

#run a test page through toscraper_scrape_reports_page and save the result
def save_test_page_known_good():
	test_page=io.open('test_pages/report_w_m_comment_m_review_edit.html',
		'r', encoding="utf-8").read()

	reports=toscraper_scrape_reports_page(test_page,"Test", log_handler,
		[], [])

	f=open('test_pages/report_w_m_comment_m_review_edit.html.json','w')
	reports=json.dumps(reports)
	f.write(reports)
	f.close()

	print('test page known good saved')

#test ToAPI.scrape_reports_page against known goods
#if this test fails, there's a change in scrape_reports_page that
#will cause a database change
def test_scrape_reports_page():
	test_page=io.open('test_pages/report_w_m_comment_m_review_edit.html','r',
		encoding="utf-8").read()
	
	reports=toscraper_scrape_reports_page(test_page,"Test", log_handler,
		[], [])

	f=io.open('test_pages/report_w_m_comment_m_review_edit.html.json','r',
		encoding="utf-8")
	known_good_reports=json.loads(f.read())
	f.close()

	if reports==known_good_reports:
		print('test_scrape_reports_page: pass')
	else:
		#figure out what's changed
		#if this throws an exception then the keys have changed
		fail_list=[]
		count=0

		if len(reports)!=len(known_good_reports):
			fail_list.append(['length_fail',len(reports),
				len(known_good_reports)])

		while(count<=len(reports)):
			report_fail_list=[]
			
			try:
				for key,value in known_good_reports[count].items():
					if reports[count][key]!=value:
						report_fail_list.append( ['value_fail',key, value, 
							reports[count][key]] )
					if type(reports[count][key])!=type(value):
						report_fail_list.append( ['type_fail',key, 
							str(type(value)), str(type(reports[count][key]))] )
			except:
				report_fail_list.append( ['key_fail'] )

			fail_list.append(report_fail_list)
			count+=1
		print('test_scrape_reports_page: fail')
		print(str(fail_list))


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("--pagestart", type=int, default=1,
		help="page number to start scraping, default: 1")

	parser.add_argument("--pageend", type=int, default=0,
		help="page number to start scraping, default: 0 (go to last page)")

	parser.add_argument("--ratelimit", type=float, default=2,
		help="max rate to request pages in seconds, default: 2")

	parser.add_argument("--orderby", type=str, default="edit",
		choices=["edit","creation"],
		help="edit: set turkopticon to order by edit mode, useful for updating;"
			" creation: set turkopticon to order by creation, useful for"
			" a fresh scrape")

	parser.add_argument("--dontstop", action="store_true",
		help="scrape will stop by default when no new data is found, regardless"
			"of pageend, pass this to disable the behavior for full scrapes")

	parser.add_argument("--dbpath", type=str, default="to.db",
		help="file path to database, if it does not exist it will be"
			" created, default: to.db" )

	parser.add_argument("--autoupdate", action="store_true",
		help="instead of closing after completing a scrape, keep alive and "
		"check for updates on interval ( set with --autoupdate_interval )")

	parser.add_argument("--autoupdate_interval", type=float, default=300,
		help="interval to check for updates in autoupdate mode, in seconds")

	parser.add_argument("--stats", action="store_true",
		help="print database stats and exit" )

	parser.add_argument("--exportdb", action="store_true",
		help="creates an export database with dropped indexes and hashes"
			" removed (they can be recreated on import), optionally specify"
			" export db path with --exportpath, will exit on completion")

	parser.add_argument("--exportpath", type=str, default="export.db",
		help="filepath to save exported database, default: export.db")

	parser.add_argument("--importdb", action="store_true",
		help="recreate missing indexes and hashes, at database pointed to by "
			"--dbpath, needed to use a previously exported database (one you "
			"downloaded), will exit on completion")

	parser.add_argument("--rebuildstats", action="store_true",
		help="regenerate the global stats table (fair,fast,pay,comm,tosviol) "
			"from the reviews table, this could take 10 minutes, will exit "
			"on completion" )

	parser.add_argument("--rebuildindexes", action="store_true",
		help='drop the indexes and rebuild them, this could improve '
			'performance, especially after an initial scrape; this will only '
			'remove and recreate indexes prefixed with "todbmanager", will '
			'exit on completion' )

	parser.add_argument("--filterblocked", action="store_true",
		help="retroactively filters blocked user ids and requester ids from "
			"database, will exit on completion" )

	parser.add_argument("--email", type=str, default="",
		help="provide login email to bypass prompt" )

	parser.add_argument("--password", type=str, default="",
		help="provide login password to bypass prompt" )

	parser.add_argument("--timeout", type=float, default=60,
		help="request timeout, defualt: 60" )

	parser.add_argument("--maxretry", type=int, default=30,
		help="maximum number of retries after a failed request" )

	parser.add_argument("--test_rehash", action="store_true",
		help="test db rehashing, checks if rehash function matches database"
			" entry, will exit on completion")

	parser.add_argument("--test_save_test_page_known_good",action="store_true",
		help="run test_pages/report_w_m_comment_m_review_edit.html through"
			" scraper and save to"
			" test_pages/report_w_m_comment_m_review_edit.html.json,"
			" will exit on completion")

	parser.add_argument("--test_scrape_reports_page", action="store_true",
		help="run test_pages/report_w_m_comment_m_review_edit.html through"
			" scraper and compare to"
			" test_pages/report_w_m_comment_m_review_edit.html.json,"
			" will exit on completion" )


	args=parser.parse_args()

	#check if database exists, if not, create it
	if os.path.isfile(args.dbpath)==False:
		print('no database found at '+args.dbpath+' creating new')
		todb_create_tables(args.dbpath)

	if args.importdb:
		print('recreating indexes and hashes on '+args.dbpath)
		todb_create_tables(args.dbpath)
		todb_rehash(args.dbpath)
		return

	if args.rebuildstats:
		todb_update_all_requester_stats(args.dbpath)
		return

	if args.rebuildindexes:
		todb_drop_indexes(args.dbpath)
		todb_create_tables(args.dbpath)
		return

	if args.stats:
		stats=todb_get_table_stats(args.dbpath)
		print ("Total Reviews: "+str(stats["total_review_rows"]))
		print ("Total Comments: "+str(stats["total_comment_rows"]))
		return

	if args.exportdb:
		try:
			todb_export_database(args.dbpath,args.exportpath)
		except:
			log_handler('error','main','todb_export_database failed:'+
				traceback.format_exc())
		return

	if args.test_rehash:
		todb_rehash(args.dbpath, TESTING=True, null_only=False)
		return

	if args.test_save_test_page_known_good:
		save_test_page_known_good()
		return

	if args.test_scrape_reports_page:
		test_scrape_reports_page()
		return

	try:
		user_blocklist=load_blocklist('block_userids')
	except:
		log_handler('error','main','unable to load user blocklist '+
			traceback.format_exc())
		return
	log_handler('info','main','loaded '+str(len(user_blocklist))+
		' blocked user ids')

	try:
		requester_blocklist=load_blocklist('block_requesterids')
	except:
		log_handler('error','main','unable to load requester blocklist '+
			traceback.format_exc())
		return
	log_handler('info','main','loaded '+str(len(requester_blocklist))+
		' blocked requester ids')

	if args.filterblocked:
		todb_delete_userids_from_db(user_blocklist, requester_blocklist)
		return

	if args.email is "":
		args.email=input("email:")

	if args.password is "":
		args.password=getpass("password(hidden):")

	session=Session()
	session_retries= Retry( total= args.maxretry, backoff_factor=4,
		status_forcelist=[ 502, 503, 504 ] )
	session.mount(to_url, HTTPAdapter(max_retries=session_retries) )

	print('logging in...')
	try:
		toscraper_login(session, to_url, args.email, args.password, 
			args.timeout)
		print('logged in:'+
			str(toscraper_check_login(session, to_url, args.timeout)) )
	except:
		log_handler('error','main','login error '+ traceback.format_exc())

	toscraper_set_orderby(session,to_url,args.orderby,args.timeout)

	try:
		if args.autoupdate:
			time_start=time.time()
			while(1==1):
				time_start=time.time()
				scrape_to(session,args.dbpath,to_url,args.pagestart,args.pageend,
					args.ratelimit,args.dontstop,args.timeout, user_blocklist, 
					requester_blocklist)
				wait_time=args.autoupdate_interval-(time.time()-time_start)
				if wait_time > 0:
					print('scrape complete, waiting '+str(wait_time)+'s')
					time.sleep(wait_time)
		else:
			scrape_to(session,args.dbpath,to_url,args.pagestart,args.pageend,
				args.ratelimit,args.dontstop,args.timeout, user_blocklist, 
				requester_blocklist)

	except(KeyboardInterrupt, SystemExit):
		log_handler('info','main','keyboard interrupt detected, closing')
		return

if __name__ == '__main__':
	main()






