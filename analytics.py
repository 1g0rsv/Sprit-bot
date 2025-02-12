import sqlite3
import pandas as pd

def load_data(db_file="fuel_prices.db"):
    """
    Загружает исторические данные о ценах и информацию о заправке, объединяя таблицы fuel_prices и stations.
    Таблица fuel_prices содержит поля: timestamp, diesel, e10, super, station_id.
    Таблица stations содержит: id, postal_code, city, station_name, unique_station_id.
    """
    conn = sqlite3.connect(db_file)
    query = """
    SELECT fp.timestamp, fp.diesel, fp.e10, fp.super,
           s.postal_code, s.city, s.station_name, s.unique_station_id
    FROM fuel_prices fp
    JOIN stations s ON fp.station_id = s.id
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def preprocess_data(df):
    """
    Преобразует столбец timestamp в datetime и добавляет столбцы:
      - day_of_week: название дня недели,
      - hour_of_day: час суток.
    """
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
    df['day_of_week'] = df['datetime'].dt.day_name()
    df['hour_of_day'] = df['datetime'].dt.hour
    return df

def compute_metrics(df, group_field):
    """
    Группирует данные по указанному полю (например, 'day_of_week' или 'hour_of_day')
    и для каждого типа топлива (diesel, e10, super) вычисляет: среднее, минимум, максимум, стандартное отклонение.
    Возвращает словарь с результатами для каждого вида топлива.
    """
    metrics = {}
    fuel_types = ['diesel', 'e10', 'super']
    grouped = df.groupby(group_field)
    for fuel in fuel_types:
        agg_metrics = grouped[fuel].agg(['mean', 'min', 'max', 'std'])
        metrics[fuel] = agg_metrics
    return metrics

def main():
    # Загружаем данные из базы данных
    df = load_data("fuel_prices.db")
    if df.empty:
        print("Нет данных для анализа.")
        return
    
    # Предобрабатываем данные: преобразуем timestamp, добавляем день недели и час суток
    df = preprocess_data(df)
    
    # Вычисляем метрики по дням недели
    day_metrics = compute_metrics(df, 'day_of_week')
    # Вычисляем метрики по часам суток
    hour_metrics = compute_metrics(df, 'hour_of_day')
    
    print("Метрики по дням недели:")
    for fuel, metrics in day_metrics.items():
        print(f"\n{fuel.upper()}:")
        print(metrics)
    
    print("\nМетрики по часам суток:")
    for fuel, metrics in hour_metrics.items():
        print(f"\n{fuel.upper()}:")
        print(metrics)

if __name__ == '__main__':
    main()