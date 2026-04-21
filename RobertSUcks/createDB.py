import mysql.connector
from security import encrypt_password

def createDatabaseFromFile():
  # Establish a connection to the MySQL server
  DB_CONFIG = {
    "host": "nurilog-db.mysql.database.azure.com",
    "port": 3306,
    "user": "tylercoleroot",
    "password": "Barker123!",
    "ssl_ca": "DigiCertGlobalRootG2.crt.pem",
    "ssl_disabled": False,
    }

    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(buffered=True)

    with open("RobertSUcks/NutrilogDB.sql", "r", encoding="utf-8") as file:
        sql_queries = file.read()

    queries = sql_queries.split(";")

    for query in queries:
        try:
            if query.strip():
                cursor.execute(query)
                conn.commit()
                print("Query executed successfully!")
        except Exception as e:
            print("Error executing query:", str(e))

    cursor.close()

    old_pass = "2222"
    secure_pass = encrypt_password(old_pass)

    fix_old_user = conn.cursor()
    fix_old_user.execute(
        "UPDATE Users SET pass_key = %s WHERE pass_key = %s",
        (secure_pass, old_pass)
    )
    conn.commit()
    fix_old_user.close()
    
    tyler_old_pass = "3333"
    tyler_secure_pass = encrypt_password(tyler_old_pass)

    fix_old_tyler = conn.cursor()
    fix_old_tyler.execute(
        "UPDATE Users SET pass_key = %s WHERE pass_key = %s",
        (tyler_secure_pass, tyler_old_pass)
    )
    conn.commit()
    fix_old_tyler.close()
    conn.close()

createDatabaseFromFile()