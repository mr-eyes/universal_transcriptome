"""
This script is used under the project "Universal Transcriptome"

Input: components CSV file (original & collective) generated by the sciprt "originalComponentsToCollectiveComponents.py"
Operation: Insert into mysql table

Run:
python mySQL_insert_components.py.py <components.csv>

"""

import sqlite3
from sqlite3 import Error
from configparser import ConfigParser
import subprocess
import time
from tqdm import tqdm
import sys
import os


def read_db_config(filename='config.ini', section='mysql'):
    parser = ConfigParser()
    parser.read(filename)
    db = {}

    if parser.has_section(section):
        items = parser.items(section)
        for item in items:
            db[item[0]] = item[1]
    else:
        raise Exception('{0} not found in the {1} file'.format(
            section, filename))

    return db


if len(sys.argv) < 2:
    sys.exit("run: python mySQL_insert_components.py <components.csv>")

components_csv = sys.argv[1]
start_time = time.time()
db_config = read_db_config()

originalCompsNo = int(
    subprocess.getoutput(f"wc -l {components_csv}").split()[0])

sqlite_db_file = "omnigraph.db"
sqliteConnection = None
no_rows = 0

try:
    sqliteConnection = sqlite3.connect(sqlite_db_file)
    cursor = sqliteConnection.cursor()
    print("Successfully Connected to SQLite")

    CREATE_TABLE = f"""
        CREATE TABLE IF NOT EXISTS `unitigs_tracker` (
            `id`	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
            `finalcomponent_id`	INTEGER,
            `collectivecomponent_id`	INTEGER,
            `originalcomponent_id`	INTEGER,
            `unitig_id`	INTEGER
        );
    """

    CREATE_INDEX = "CREATE INDEX components_index ON unitigs_tracker (finalcomponent_id, collectivecomponent_id, originalcomponent_id, unitig_id);"

    sqliteConnection.execute(CREATE_TABLE)
    sqliteConnection.execute(CREATE_INDEX)
    sqliteConnection.commit()

    print("Please wait, the progress bar will start shortly ...")

    with open(components_csv, 'r') as componentsReader:
        for line in tqdm(componentsReader, total=originalCompsNo):
            line = line.strip().split(',')
            original_compID = line[0]
            collective_compID = line[1]
            for unitig_id in line[2:]:

                sqliteConnection.execute(
                    f'INSERT INTO unitigs_tracker(id, unitig_ID,originalComponent_ID,collectiveComponent_ID,finalComponent_ID) VALUES(NULL, {unitig_id}, {original_compID}, {collective_compID}, 0)'
                )
                no_rows += 1

    sqliteConnection.commit()

    print(f"{no_rows} rows inserted successfully into unitigs_tracker table ",
          cursor.rowcount)
    cursor.close()

except sqlite3.Error as error:
    print("Failed to insert data into sqlite table", error)
finally:
    if (sqliteConnection):
        sqliteConnection.close()
        print("The SQLite connection is closed")

print(
    f"{originalCompsNo} components inserted in {(time.time() - start_time)} secs"
)
