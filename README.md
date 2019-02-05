todbmanager is a utility to scrape turkopticon into a database, and assist in maintaining that 
database.

The database provided here is released under the following terms from Turkopticon: "Authorized for personal Mechanical Turk worker use only, at the discretion of TurkOpticon. All other use prohibited without express consent." 


At the moment, it only collects from turkopticon.ucsd.edu, it doesn't work for TO 2.0 at 
turkopticon.info


This is an early version, and the code may change often. There will likely be bugs, but
this version succesfully did a full scrape on turkopticon.ucsd.edu without any problems.


If your just interested in the database, it's currently available at:


## INSTALLATION


todbmanager is written for python2.7, and requires a few libraries that aren't part of the
standard library. These libraries can be installed from your distributions package manager
(linux), or with pip. 


The non-standard libraries are:


mechanize - http://wwwsearch.sourceforge.net/mechanize/


bs4 - https://www.crummy.com/software/BeautifulSoup/bs4/doc/


Detailed installation instructions are big todo, but if your on linux, you should
have no problems getting this up and running. This hasn't been tested yet on windows
or osx. 


Once python and the libraries are installed, just download and extract the source files. You
can start the manager with:
$python2.7 todbmanager.py


## OPERATION
At the moment todbmanager uses a simple CLI interface. There are no command line
parameters. When it prompts you for selections, type them in and press enter. 
Default options will be in parenthesis.


~~On first run, it will detect that it doesn't have a database, and ask you if you~~
~~want to download one. The full database is currently on the wiki, this is where~~
~~it will download it from. If you say yes, it will download, unzip and start using~~
~~this database. If you say no, it will start a new one.~~

This is disabled at the moment. To download the database for use with todbmanager,
download from the releases area, extract into the directory you downloaded todbmanager,
and rename the file to: to.db
If you've already started todbmanager and it created an empty database, just delete it.


Doing a full scrape takes a lot of time (8-12 hours). There won't be a need to do
a full scrape if you choose to download the database, you can just use the auto-update
option. The rundown of the current options is below.


#### Update Database
This is the scraping function. It scrapes TO, checks for new reports, comments, edits, etc, 
and enters the information into the database. It runs a self test (see Run Tests) to make sure 
everything runs the way it should, and then asks for several configuration options. If
any of the tests fail, it won't let you continue. 

###### Email:
Reports pages are behind a login, the mechanize browser uses this to login.
This isn't saved and is only used to login the browser.

###### Pass:
Same as email. This uses the python getpass function which doesn't display
the password or any characters at all as you type it in. Just type it in and
press enter.

###### auto-update:
This will determine how todbmanager runs the scrape. 
type y for auto update, n for no autoupdate, or just press enter for the default
(auto-update)

In auto-update mode, todbmanager toggles turkopticon to "Order by edit date", and then scrapes 
as far as it's getting new data. The scrape will stop once it detects nothing has changed on the 
current page. If you downloaded the database on first start, this will get you all the latest 
data, without having to scrape the full database. If your starting from scratch, all data will 
be new data, and it will go all the way to the end. Don't use this function to scrape a database 
from scratch though, as "Order by edit date" will bump new, modified, or reviews with new comments 
to the top of the page list mid scrape, and you'll end up with missing data. 

With auto-update set to no, todbmanager toggles turkopticon to "Order by creation date", and
will scrape all pages between page start and page end. It will not stop when it detects no new
data.

###### page start:
This is the page to start scraping, the default is 1. Setting this to something besides 1 is
useful in auto-update off mode when you have to stop mid-scrape, and want to pick up where
you left off. 

###### page end:
This is the page to stop scraping. It should be fine to use the default of 0 in all cases.
When page end is set to 0, it automatically updates to the last page currently on turkopticon,
and does this after every scrape. Considering full scrapes take 10 hours, new reviews will come
in while it's in progress, and this ensures that it gets the last few pages of data. In auto-update
mode with the downloaded database, auto-update will never get close to the end, so it's safe to
leave it at the default. Auto-update will respect the page end though if it's set to something
besides 0. Even if it's getting new data, auto-update will stop at the page end. 

###### rate limit:
This is the maximum rate limit to send page requests to turkopticon in seconds. The default is 2.0. 
In reality, you'll rarely ever exceed this, in testing turkopticon rarely serves pages faster
than 2s. Page requests currently aren't multiprocessed, so it'll never request pages faster than
turkopticon serves them on an individual basis, even if the rate limit is set below the serve rate. 

After these configuration options, todbmanager will begin the scrape. You can press ctrl+c at any
time to stop it, and it should handle it gracefully. If it doesn't, you can keep pressing ctrl+c 
and python will kill the process all together. This shouldn't cause any database corruption.

#### Update Stats
This gives some basic database stats. Currently it's the number of reviews and comments in the tables.

#### Delete Blocked Ids from Database
todbmanager has the capability to ignore specific user ids. You can enter these in the blocked_userids 
file in the source directory, and it will be read on initialization. Enter them 1 ID per line. Blocked
ids read from this file will not be entered into the database during a scrape. If you want to delete
them retroactively, use this function. Userids must be hased with sha256 prior to being entered in the
file. 

#### Delete Database
This will drop the database tables and recreate them. It won't delete the database file. You will loose
all data doing this. It will ask you to enter DELETE to confirm, or just press enter to go back.

#### Download Database
This will re-download the database from the wiki. It will delete the current database file
if there is one. It will ask you to enter DOWNLOAD to confirm, or just press enter to go back. 

#### Run Tests
This is mainly for debugging. Run Tests should always pass on release code. This function will also be
run before "Update Database" begins, and if it detects a failure it will prevent updating.
If a failure is detected during Run Tests scraping functions may comprimise existing database data.


## NOTES

#### I'm a turkopticon user, I don't want my reviews / comments included
-Post at https://turkopticon.ucsd.edu/forum/show_post/1813 and state that you do not want your reviews included

-Include a \[NODB\] tag in one of your reviews, just type \[NODB\] anywhere in any one of your reviews,
you don't have to include it in every one.

-Send me an email directly at toutils1@yandex.com, with a link to one of your reviews that include a \[NODB\] tag. 

The blocked userids list will be released along with the source, to indicate to anyone else who wants to maintain a 
database that these users do not wish to be included. The scraper will honor the blocked userids list by default. 

It's up to the individual user to decide whether or not they want to respect these filtering lists for their own databases.
Databases released here will respect the block lists.


#### I'm a requester and I don't want the reviews about me included. 
This is to be determined at the discretion of Turkopticon. Any requesters filtered from the database will
have their requester id's included in a blocked requester ids file; which the scraper will honor by default.
It's up to the individual user to decide whether or not they want to respect these filtering lists for their own databases.
Databases released here will respect the block lists.

#### I don't care about block lists, I want all of the review data
Using the block lists will always be a configuration option. todbmanager will always be configured by default
in a way that matches the release databases. If you want a full database that hasn't been filtered with these
lists, you'll be able to turn off the filtering in configuration, and then do a full database update.


#### Frequent Code Changes / Database Locations
This is still a very early version and the code is expected to change frequently. If something stops working
check back here. 


#### Tests/Database Changes
"Run Tests" relies on known good data from the test_pages directory. New updates may change this data,
if the way the scraper handles data needs to be changed. If this change happens, then duplicate/modification
checking may not work with the existing database, even though the test passes. All reviews will end up being 
flagged as modified, and auto-update will scrape all the way to the end. In this case, downloading a new database 
instead is highly suggested. If the code is updated in this way, a new database will be released along with it.

#### Hidden Reviews
todbmanager currently does not scrape for hidden reviews. This is a planned feature. Hidden reviews require
having a full database first, and then hitting each requester id individually. This will double the already
long process of doing a full scrape. A new database will be released with these reviews when the feature is
added.

#### Auto Update and Modified Comments / Hidden Reviews
Modified comments do not cause a review to be bumped to the first page when "Toggle by edit date" is set. 
New reviews, modified reviews, or reviews with new comments are. This means that auto-update will not be 
effective to catch all modified comments, the only way to do this is to do a full scrape. When the hidden reviews
scraping is added, it will be in a seperate function, auto-update will not apply. It's not known if
toggling comments from flag to comment will bump a review to the top. If it doesn't, then it's no different
than modified comments. It's also not known if a review gets bumped to the first page when it get's unhidden.
If it doesn't, this data may not be captured until the next full scrape.

#### Multiprocessing
Currently scraping and database operations are run in a seperate process during a scrape, but requests are not.
In future updates, full multiprocessing may be used, where multiple requests can be sent and processed at once.
This would cause additional server load for turkopticon though, and there may be problems with duplicate checking
and missing data depending on how fast reviews are coming in during the scrape, which is why the existing
method was used instead.

#### Database Updates
I plan on releasing monthly updates that have been fully re-scraped (to capture modified comments, hidden reviews,
and unhidden reviews), and possibly weekly updates that have been kept up to date with auto-update.

#### Toggle by Edit/Creation Date
Turkopticon stores this setting on the server side. todbmanager will only toggle this to the correct setting once,
before a scrape starts. If you login with a normal browser and change this toggle, it will affect the data that
todbmanager is getting too. A future update will likely address this, detecting a change every scrape and setting
it back to the correct one if it gets changed.

 
