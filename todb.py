import sqlite3
import traceback
import os
import shutil
import json
import hashlib

class todbException(Exception):
	def __init__(self, message):
		self.message=message

#read key/value data from meta table
def todb_read_meta(dbpath, key):
	conn=sqlite3.connect(dbpath)
	cursor=conn.cursor()
	
	cursor.execute("SELECT key,value FROM meta WHERE "
		"key=?",(key,))
	value=cursor.fetchone()
	conn.close()
	return value

def todb_write_meta(dbpath, meta_key, meta_value):
	conn=sqlite3.connect(dbpath)
	cursor=conn.cursor()
	#check if it exists first
	cursor.execute("SELECT key,value FROM meta WHERE "
		"key=?",(meta_key,))
	value=cursor.fetchone()

	if value==None:
		cursor.execute("INSERT INTO meta VALUES (?,?)",(meta_key,meta_value))
		op='insert'
	else:
		cursor.execute("UPDATE meta SET value=? WHERE key=?",(meta_key,
			meta_value))
		op='update'
	conn.commit()
	conn.close()
	return op


def todb_create_tables(dbpath):
	conn=sqlite3.connect(dbpath)
	cursor=conn.cursor()
	

	print ('creating meta table if needed...')
	cursor.execute("create table if not exists meta (key text, value text)")
	conn.commit()

	#add database meta data, check version first
	#if key "version" exists at all, it isn't a fresh database, don't add
	#meta data, it's already there
	version=todb_read_meta(dbpath, "version")
	print('found version:'+str(version))
	if version is None:
		print('version not found, assuming new database')
		todb_write_meta(dbpath, "version","1")


	#stats table for requester total aggregated across reviews
	print('creating stats table if needed...')
	cursor.execute("create table if not exists stats ( "
		"requester_id text not null unique, requester_name text, fair real, " 
		"fast real, pay real, comm real, tosviol integer, numreviews integer)" )

	print('creating stats table indexes...')
	cursor.execute("CREATE INDEX IF NOT EXISTS todbmanager_stats_covering ON "
		"stats (requester_id, requester_name, fair, fast, pay, comm, "
		"tosviol, numreviews)")
	
	print ('creating reviews table if needed...')
	cursor.execute ("create table if not exists reviews (requester_id text, "
					"requester_name text, fair integer, fast integer, "
					"pay integer, comm integer,review text, review_id text, "
					"date text, notes text, user_id text, tosviol integer, "
					"hidden integer,comment_hash text, review_hash text)")
	
	#used by delete_userids_from_db
	print ('creating reviews indexes if needed...')
	cursor.execute ("CREATE INDEX IF NOT EXISTS "
					"todbmanager_reviews_user_id_index ON "
					"reviews (user_id)")
	cursor.execute ("CREATE INDEX IF NOT EXISTS "
					"todbmanager_reviews_requester_id_index ON "
					"reviews (requester_id) ")
	cursor.execute ("CREATE INDEX IF NOT EXISTS "
					"todbmanager_reviews_date_index ON "
					"reviews (requester_id) ")

	#used by everything using requester stats
	cursor.execute("CREATE INDEX IF NOT EXISTS "
		"todbmanager_reviews_stats ON "
		"reviews (requester_id, requester_name, fair, fast, pay, comm, "
		"tosviol)")
	
	#used by add_to_table
	cursor.execute ("CREATE INDEX IF NOT EXISTS "
		"todbmanager_reviews_review_id_comment_hash_review_hash_index ON "
		"reviews (review_id, comment_hash, review_hash)")
	
	print ('creating comments table if needed...')
	cursor.execute ("create table if not exists comments ("
			"p_key_review integer, review_id text, type text, comment text, "
			"date text, user_id text,notes text)")
	
	print ('creating comments index if needed...')
	#used by add_to_table
	cursor.execute ("CREATE INDEX IF NOT EXISTS "
					"todbmanager_comments_p_key_review_index ON "
					"comments (p_key_review) ")
	
	cursor.execute ("CREATE INDEX IF NOT EXISTS "
					"todbmanager_comments_review_id_index ON "
					"comments (review_id) ")
	#used by delete_userids_from_db
	cursor.execute ("CREATE INDEX IF NOT EXISTS "
					"todbmanager_comments_user_id_index ON comments (user_id) ")
	
	conn.commit()
	conn.close()

def todb_get_table_stats(dbpath):
	conn=sqlite3.connect(dbpath)
	cursor=conn.cursor()
	print ('counting reviews...')
	cursor.execute ('''SELECT Count(*) FROM reviews''')
	row=cursor.fetchone()
	total_review_rows=row[0]
	
	print ('counting comments...')
	cursor.execute ('''SELECT Count(*) FROM comments''')
	row=cursor.fetchone()
	total_comment_rows=row[0]
	
	stats_dict={}
	stats_dict['total_review_rows']=total_review_rows
	stats_dict['total_comment_rows']=total_comment_rows
	
	conn.close()
	
	return stats_dict

def todb_drop_indexes(dbpath):
	conn=sqlite3.connect(dbpath, timeout=60)
	cursor=conn.cursor()

	print('dropping indexes...')
	cursor.execute("""SELECT name FROM sqlite_master """
						  """WHERE type == "index" """)
	row=cursor.fetchone()
	
	index_list=[]
	while(row!=None):
		if 'todbmanager' in row[0]:
			index_list.append(row[0])
			print('found:'+str(row[0]))
		row=cursor.fetchone()
	for i in index_list:
		print('dropping '+str(i)+'...')
		cursor.execute('DROP INDEX '+str(i))

	conn.commit()
	conn.close()

def todb_export_database(dbpath,export_filepath):
	#abort if export_filepath already exists
	if os.path.isfile(export_filepath)==True:
		raise todbException(export_filepath+' exists')

	print('copying database to '+export_filepath+' ...')
	shutil.copyfile(dbpath,export_filepath)

	#read the new database and drop the indexes if they exist
	export_conn=sqlite3.connect(export_filepath,timeout=60)
	export_cursor=export_conn.cursor()

	todb_drop_indexes(export_filepath)

	print('setting review_hash to null...')
	export_cursor.execute('UPDATE reviews SET review_hash=null;')
	export_conn.commit()
	print('setting comment_hash to null...')
	export_cursor.execute('UPDATE reviews SET comment_hash=null;')
	export_conn.commit()

	print('vacuuming...')
	export_cursor.execute('VACUUM')
	export_conn.commit()
	export_conn.close()
	print('export complete')

def todb_rehash(db_filepath, TESTING=False, null_only=True):
	print('checking database hashes...')
	print('Testing:'+str(TESTING))
	print('Null Only:'+str(null_only))
	total_reviews=0
	total_review_pass=0
	total_review_fail=0
	total_comment_pass=0
	total_comment_fail=0
	total_skipped=0;

	conn=sqlite3.connect(db_filepath)
	cursor=conn.cursor()
	comment_cursor=conn.cursor()
	update_cursor=conn.cursor()

	cursor.execute("SELECT rowid, comm, comment_hash, date, fair, fast, "
					"hidden, notes, pay, requester_id, requester_name, review, "
					"review_hash, review_id, tosviol, user_id FROM reviews")

	row=cursor.fetchone()
	while(row):
		review_dict={}
		review_rowid=row[0]
		review_dict['comm']=row[1]
		review_dict['comment_hash']=row[2]
		review_dict['date']=row[3]
		review_dict['fair']=row[4]
		review_dict['fast']=row[5]


		#SQLITE STORES TRUE/FALSE AS 0/1
		#SCRAPER HASHES WITH TRUE/FALSE IN JSON
		#WILL CAUSE MISMATCH
		review_dict['hidden']=row[6]
		if review_dict['hidden']==0:
			review_dict['hidden']=False
		elif review_dict['hidden']==1:
			review_dict['hidden']=True

		review_dict['notes']=row[7]
		review_dict['pay']=row[8]
		review_dict['requester_id']=row[9]
		review_dict['requester_name']=row[10]
		review_dict['review']=row[11]

		#do not save this in the dict yet
		old_review_hash=row[12]

		if(null_only==True):
			if(old_review_hash!=None and review_dict['comment_hash']!=None):
				total_skipped+=1

				if (total_skipped % 100000 and total_skipped>0 )==0:
					print('reviews skipped:'+str(total_skipped))

				row=cursor.fetchone()
				continue

		#review_dict['review_hash']=row[11]
		review_dict['review_id']=row[13]

		#SQLITE STORES TRUE/FALSE AS 0/1
		#SCRAPER HASHES WITH TRUE/FALSE IN JSON
		#WILL CAUSE MISMATCH
		review_dict['tosviol']=row[14]
		if review_dict['tosviol']==0:
			review_dict['tosviol']=False
		elif review_dict['tosviol']==1:
			review_dict['tosviol']=True

		review_dict['user_id']=row[15]

		comment_list=[]
		comment_cursor.execute("SELECT comment,date,notes,type,user_id FROM "
							"comments WHERE p_key_review=?",(review_rowid,))
		comment_row=comment_cursor.fetchone()
		while(comment_row):
			comment_dict={}
			comment_dict['comment']=comment_row[0]
			comment_dict['date']=comment_row[1]
			comment_dict['notes']=comment_row[2]
			comment_dict['type']=comment_row[3]
			comment_dict['user_id']=comment_row[4]
			comment_list.append(comment_dict)
			comment_row=comment_cursor.fetchone()

		comment_hash_str=''
		for comment in comment_list:
			comment_hash_str+=json.dumps(comment, sort_keys=True)
		#comment_hash=unicode(hashlib.sha256(comment_hash_str).hexdigest())
		comment_hash=hashlib.sha256(
			comment_hash_str.encode('utf-8')).hexdigest()
		if(TESTING):
			if comment_hash==review_dict['comment_hash']:
				#print 'COMMENT HASH REGEN PASS'
				total_comment_pass+=1
			else:
				print ('COMMENT HASH REGEN FAIL')
				print ('new:'+comment_hash)
				print ('old:'+review_dict['comment_hash'])
				print ('comment_hash_str: '+comment_hash_str)
				total_comment_fail+=1

		review_dict['comment_hash']=comment_hash
		review_dict['comments']=comment_list
			
		#review_hash=unicode(hashlib.sha256(json.dumps(
			#review_dict, sort_keys=True)).hexdigest())
		review_hash=hashlib.sha256(json.dumps(
			review_dict, sort_keys=True).encode('utf-8')).hexdigest()
		if(TESTING):
			if review_hash==old_review_hash:
				#print 'REVIEW HASH REGEN PASS'
				total_review_pass+=1
			else:
				print ('REVIEW HASH REGEN FAIL')
				print ('new:'+review_hash)
				print ('old:'+old_review_hash)
				print (json.dumps(review_dict, sort_keys=True, indent=4))
				total_review_fail+=1

		review_dict['review_hash']=review_hash

		if not TESTING:
			update_cursor.execute("UPDATE reviews SET review_hash=?, "
									"comment_hash=? WHERE rowid=?",
				(review_dict['review_hash'], review_dict['comment_hash'], 
					review_rowid))
		
		total_reviews+=1
		if (total_reviews % 10000 and total_reviews>0 )==0:
			print('reviews processed:'+str(total_reviews))
		row=cursor.fetchone()
		
	if not TESTING:
		print('committing...')
		conn.commit()
	print('rehash stats')
	if (TESTING):
		print('comments_hash_passed:'+str(total_comment_pass)+'/'+
			str(total_reviews))
		print('comments_hash_failed:'+str(total_comment_fail)+'/'+
			str(total_reviews))
		print('reviews_passed:'+str(total_review_pass)+'/'+str(total_reviews))
		print('reviews_failed:'+str(total_review_fail)+'/'+str(total_reviews))
		print('total_skipped::'+str(total_skipped))
	else:
		print('total processed:'+str(total_reviews))
		print('total skipped:'+str(total_skipped))

#given a list of userids, scan the database and retroactively delete
#reviews and comments
#userids and requesterids must be []
def todb_delete_userids_from_db(dbpath,log_handler,userids, requester_ids):
	conn=sqlite3.connect(dbpath,timeout=60)
	cursor=conn.cursor()
	
	print('deleting '+str(len(userids))+' user_ids...')
	
	#delete all reviews that match one of the userids
	#don't use WHERE user_id IN, limit of 999
	
	for userid in userids:
		#cursor.execute('SELECT * FROM reviews WHERE user_id=?',(userid,) )
		cursor.execute('DELETE FROM reviews WHERE user_id=?',(userid,) )
		print('user_id:'+str(userid)+' deleting '+str(cursor.rowcount)+
			' reviews')
		conn.commit()
		cursor.execute('DELETE FROM comments WHERE user_id=?',(userid,) )
		print('user_id:'+str(userid)+' deleting '+str(cursor.rowcount)+
			' comments')
		conn.commit()

	print('deleting '+str(len(requester_ids))+' requester_ids...')
	
	#delete all reviews that match one of the requesterids
	#don't use WHERE user_id IN, limit of 999
	review_ids=[]	
	for requester_id in requester_ids:
		#get the review_ids first to delete all the comments
		review_ids=[]
		cursor.execute('SELECT review_id FROM reviews WHERE requester_id=?',
			(requester_id,) )		
		row=cursor.fetchone()
		while(row!=None):
			review_ids.append(row[0])
			row=cursor.fetchone()
		print('found '+str(len(review_ids))+' review_ids')

		cursor.execute('DELETE FROM reviews WHERE requester_id=?',
			(requester_id,) )
		print('requester_id:'+str(requester_id)+' deleting '+
			str(cursor.rowcount)+' reviews')
		conn.commit()

		#delete the comments with the review_ids
		for review_id in review_ids:
			cursor.execute('DELETE FROM comments WHERE review_id=?',
				(review_id,) )
			print('review_id:'+str(review_id)+' deleting '+
				str(cursor.rowcount)+' comments')
			conn.commit()

	conn.close()

#update stats for a requester id
#add stats if they don't exist
def todb_update_requester_stats(dbpath, requester_id):

	conn=sqlite3.connect(dbpath,timeout=60)
	search_cursor=conn.cursor()
	mod_cursor=conn.cursor()

	#calculate global stats from reviews
	a_fair=0.0
	c_fair=0
	a_fast=0.0
	c_fast=0
	a_pay=0.0
	c_pay=0
	a_comm=0.0
	c_comm=0
	t_tosviol=0
	numreviews=0
	requester_name=""

	search_cursor.execute("SELECT requester_name,fair,fast,pay,comm,tosviol FROM reviews "
		"WHERE requester_id=?", (requester_id,))
	row=search_cursor.fetchone()
	if row is not None:
		while(row is not None):
			numreviews+=1
			if row[1] is not None:
				a_fair+=row[1]
				c_fair+=1
			if row[2] is not None:
				a_fast+=row[2]
				c_fast+=1
			if row[3] is not None:
				a_pay+=row[3]
				c_pay+=1
			if row[4] is not None:
				a_comm+=row[4]
				c_comm+=1
			if row[5] is not None:
				t_tosviol+=row[5]
			#the stats requester_name will end up being the last one inserted
			requester_name=row[0]
			row=search_cursor.fetchone()

		if c_fair==0:
			a_fair=None
		else:
			a_fair=float(a_fair)/float(c_fair)
		
		if c_fast==0:
			a_fast=None
		else:
			a_fast=float(a_fast)/float(c_fast)

		if c_pay==0:
			a_pay=None
		else:		
			a_pay=float(a_pay)/float(c_pay)

		if c_comm==0:
			a_comm=None
		else:
			a_comm=float(a_comm)/float(c_comm)

	else:
		#this should never happen, if this is the first review, the review
		#should have been commited to the review table prior to running this
		#function
		raise todbException('no reviews in reviews table for '+requester_id)

	#check stats table for existing
	search_cursor.execute("SELECT rowid FROM stats WHERE requester_id=?",
		(requester_id,))
	row=search_cursor.fetchone()
	if row is None: #first stats, insert	
		mod_cursor.execute('INSERT INTO stats VALUES '
				'(?,?,?,?,?,?,?,?)',(requester_id, requester_name, a_fair, a_fast,
				a_pay, a_comm, t_tosviol,numreviews))
	else: #stats already exist, update
		mod_cursor.execute("UPDATE stats SET requester_name=?, fair=?, fast=?, "
			"pay=?, comm=?, tosviol=?, numreviews=? WHERE requester_id=?",
			(requester_name, a_fair,a_fast,a_pay,a_comm,t_tosviol,requester_id,
			numreviews))

	conn.commit()
	conn.close()

#update every single requester id, useful for import
#NOTE some reviews don't have requester ids,or names, confirmed by cross 
#referencing user reviews. The only way these are accessible is via the main
#page, or on a user's review page ( https://turkopticon.ucsd.edu/by/{userid}
def todb_update_all_requester_stats(dbpath):
	conn=sqlite3.connect(dbpath,timeout=60)
	search_cursor=conn.cursor()
	print('generating requester_id list...')
	search_cursor.execute("SELECT DISTINCT requester_id FROM reviews")
	requester_ids=search_cursor.fetchall()
	total_ids=len(requester_ids)
	print('found '+str(total_ids))
	progress=0
	skipped=0

	print('updating requester stats table...')
	for req_id in requester_ids:
		todb_update_requester_stats(dbpath, req_id[0])
			
		progress+=1
		if (progress % 1000 and total_ids>0 )==0:
			print(str(progress)+'/'+str(total_ids)+' complete')

	print('stats update complete')	

	conn.close()
	

#add a report to a table
#check for duplicates, return added,modified,none
#takes a mod_cursor to support bulk commits, speeds up sqlite inserts
def todb_add_to_table(dbpath,report, log_handler):
	mod_conn=sqlite3.connect(dbpath,timeout=60)
	mod_cursor=mod_conn.cursor()
	search_cursor=mod_conn.cursor()

	status=None
	comments_modified=0
	
	#check if it already exists in the table
	#review_id may not be accurate, instead compare with user_id and
	#requester_id
	#if match, update instead of add.
	search_cursor.execute('SELECT rowid,comment_hash,review_hash FROM '
		'reviews WHERE review_id=?',(report['review_id'],) )
	row=search_cursor.fetchone()
	
	if row==None:   #brand new review, not edited
		mod_cursor.execute('INSERT INTO reviews VALUES '
			'(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(report['requester_id'],
			report['requester_name'],report['fair'],report['fast'],
			report['pay'],report['comm'],report['review'],report['review_id'],
			report['date'],report['notes'],report['user_id'],report['tosviol'], 
			report['hidden'],report['comment_hash'],report['review_hash']))
		mod_conn.commit()
		todb_update_requester_stats(dbpath, report['requester_id'])		

		#lastrowid onliy works for the last insert, not update or anything else
		p_key_review=mod_cursor.lastrowid
		if(p_key_review==None):
			print("ERROR: NEW REVIEW P_KEY_REVIEW NULL")

		for comment in report['comments']:
			mod_cursor.execute('INSERT INTO comments VALUES (?,?,?,?,?,?,?)',
				(p_key_review,report['review_id'],comment['type'],
				comment['comment'],comment['date'],comment['user_id'],
				comment['notes']))
			mod_conn.commit()
			comments_modified+=1
			
		status='added'
	
	#a review was found matching review_id, check if review hash 
	#matches for changes
	else: 
		#the review has been changed, update
		if str(row[2])!=str(report['review_hash']):

			mod_cursor.execute( 'UPDATE reviews SET requester_id=?, '
				'requester_name=?, fair=?, fast=?, pay=?, comm=?, review=?, '
				'review_id=?,date=?,notes=?, user_id=?, tosviol=?, hidden=?, '
				'comment_hash=?, review_hash=? WHERE rowid=?',
				(report['requester_id'],report['requester_name'],report['fair'],
				report['fast'],report['pay'], report['comm'],report['review'],
				report['review_id'],report['date'],report['notes'],
				report['user_id'],report['tosviol'],report['hidden'],
				report['comment_hash'], report['review_hash'], row[0]))
			mod_conn.commit()

			todb_update_requester_stats(dbpath, report['requester_id'])

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
					log_handler('ERROR','worker:add_to_table',
						'comments p_key_review is null')
				
				mod_cursor.execute('DELETE FROM comments WHERE p_key_review=?',
					(p_key_review,) )
				for comment in report['comments']:
					mod_cursor.execute('INSERT INTO comments VALUES '
					'(?,?,?,?,?,?,?)',
					(p_key_review,report['review_id'],comment['type'],
					comment['comment'],comment['date'],comment['user_id'],
					comment['notes']))
					comments_modified+=1
				mod_conn.commit()
	
	return {'status':status,'comments_modified':comments_modified}



