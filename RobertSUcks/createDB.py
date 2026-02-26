import mysql.connector
from security import encrypt_password, decrypt_password

def createDatabaseFromFile():
  # Establish a connection to the MySQL server
  DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "Barker123!"  
    }
  
  conn = mysql.connector.connect(**DB_CONFIG)

  # Create a cursor to execute queries
  cursor = conn.cursor(buffered=True)

  # Open and read the SQL file
  with open('RobertSUcks/NutrilogDB.sql', 'r') as file:
      sql_queries = file.read()

  # Split the SQL file content into individual queries
  queries = sql_queries.split(';')

  # Iterate over the queries and execute them
  for query in queries:
      try:
          if query.strip() != '':
              cursor.execute(query)
              conn.commit()
              print("Query executed successfully!")
      except Exception as e:
          print("Error executing query:", str(e))

  # Close the cursor and the database connection
  cursor.close()
  
  #taking old sample password and encrypting it
  old_pass = '2222'
  secure_pass = encrypt_password(old_pass)
  
  fix_old_user = conn.cursor()
  #then executing a statement to update that old password with our encryption
  fix_old_user.execute(
    "UPDATE Users SET pass_key = %s WHERE pass_key = %s",
    (secure_pass, old_pass,)
  )
  #close cursor
  fix_old_user.close()
  #commit to db and close connection
  conn.commit()
  conn.close()

createDatabaseFromFile()
