import sqlite3

DB_FILE = "fuel_data.db"  # Убедитесь, что имя файла совпадает с тем, что используется в collector.py

def read_all_data(db_file=DB_FILE):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM fuel_prices")
    rows = cursor.fetchall()
    conn.close()
    return rows

if __name__ == '__main__':
    data = read_all_data()
    for row in data:
        print(row)