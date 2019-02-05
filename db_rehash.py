import sqlite3
import hashlib
import json


def db_rehash(db_filepath, TESTING=False, null_only=True):
	print('Testing:'+str(TESTING))
	print('Null Only:'+str(null_only))
	total_reviews=0
	total_comments=0
	total_review_pass=0
	total_review_fail=0
	total_comment_pass=0
	total_comment_fail=0
	total_skipped=0;

	conn=sqlite3.connect(db_filepath)
	cursor=conn.cursor()
	comment_cursor=conn.cursor()
	update_cursor=conn.cursor()

	cursor.execute('''SELECT rowid, comm, comment_hash, date, fair, fast, hidden, notes, pay, requester_id, requester_name,
		review, review_hash, review_id, tosviol, user_id FROM reviews''')

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

				if (total_skipped % 10000 and total_skipped>0 )==0:
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
		comment_cursor.execute('''SELECT comment,date,notes,type,user_id FROM comments WHERE p_key_review=?''',(review_rowid,))
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
			total_comments+=1

		comment_hash_str=''
		for comment in comment_list:
			comment_hash_str+=json.dumps(comment, sort_keys=True)
		comment_hash=unicode(hashlib.sha256(comment_hash_str).hexdigest())

		if(TESTING):
			if comment_hash==review_dict['comment_hash']:
				#print 'COMMENT HASH REGEN PASS'
				total_comment_pass+=1
			else:
				print 'COMMENT HASH REGEN FAIL'
				print 'new:'+comment_hash
				print 'old:'+review_dict['comment_hash']
				print 'comment_hash_str: '+comment_hash_str
				total_comment_fail+=1

		review_dict['comment_hash']=comment_hash
		review_dict['comments']=comment_list
			
		review_hash=unicode(hashlib.sha256(json.dumps(review_dict, sort_keys=True)).hexdigest())

		if(TESTING):
			if review_hash==old_review_hash:
				#print 'REVIEW HASH REGEN PASS'
				total_review_pass+=1
			else:
				print 'REVIEW HASH REGEN FAIL'
				print 'new:'+review_hash
				print 'old:'+old_review_hash
				print json.dumps(review_dict, sort_keys=True, indent=4)
				total_review_fail+=1

		review_dict['review_hash']=review_hash

		if not TESTING:
			update_cursor.execute('''UPDATE reviews SET review_hash=?, comment_hash=? WHERE rowid=?''',
				(review_dict['review_hash'], review_dict['comment_hash'], review_rowid))
		
		total_reviews+=1
		if (total_reviews % 10000 and total_reviews>0 )==0:
			print('reviews processed:'+str(total_reviews))
		row=cursor.fetchone()
		
	if not TESTING:
		print('committing...')
		conn.commit()
	print('rehash stats')
	if (TESTING):
		print('comments_hash_passed:'+str(total_comment_pass)+'/'+str(total_comments))
		print('comments_hash_failed:'+str(total_comment_fail)+'/'+str(total_comments))
		print('reviews_passed:'+str(total_review_pass)+'/'+str(total_reviews))
		print('reviews_failed:'+str(total_review_fail)+'/'+str(total_reviews))
		print('total_skipped::'+str(total_skipped))
	else:
		print('total processed:'+str(total_reviews))
		print('total skipped:'+str(total_skipped))

if __name__ == '__main__':
	db_rehash("ramfs/to_testing.db", TESTING=True, null_only=False)
