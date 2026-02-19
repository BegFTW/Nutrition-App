import mysql.connector

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
  cursor = conn.cursor()

  # Open and read the SQL file
  with open('NutrilogDB.sql', 'r') as file:
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
  conn.close()

createDatabaseFromFile()