from datetime import datetime
from statistics import median

import pandas as pd
from psycopg2 import sql

from app import app, database as db
from app.data_service.models import DataLoader
from app.history.models import History


class DataTransformer:
    def __init__(self, dbconnection):
        self.dbconnect = dbconnection

    def impute_missing_data_on_average(self, schema_id, table, column):
        """" impute missing data based on the average"""
        try:
            schema_name = 'schema-' + str(schema_id)
            cursor = self.dbconnect.get_cursor()

            query = cursor.mogrify(sql.SQL('SELECT AVG( {} ) FROM {}.{}').format(
                sql.Identifier(column),
                sql.Identifier(schema_name),
                sql.Identifier(table)
            ))
            cursor.execute(query)

            average = cursor.fetchone()[0]
            if not average:
                average = 0

            query = cursor.mogrify(sql.SQL('UPDATE {}.{} SET {}= %s WHERE {} IS NULL;').format(
                sql.Identifier(schema_name),
                sql.Identifier(table),
                sql.Identifier(column),
                sql.Identifier(column)
            ), (average,))
            cursor.execute(query)
            self.dbconnect.commit()
        except Exception as e:
            app.logger.error("[ERROR] Unable to impute missing data for column {} by average".format(column))
            app.logger.exception(e)
            self.dbconnect.rollback()
            raise e

    def impute_missing_data_on_median(self, schema_id, table, column):
        """" impute missing data based on the average"""
        try:
            schema_name = 'schema-' + str(schema_id)
            cursor = self.dbconnect.get_cursor()

            query = cursor.mogrify(sql.SQL('SELECT {} FROM {}.{}').format(
                sql.Identifier(column),
                sql.Identifier(schema_name),
                sql.Identifier(table)
            ))
            cursor.execute(query)
            values = list()
            for value in cursor:
                if value[0] is not None:
                    values.append(value[0])

            if (len(values)) == 0:
                median_val = 0
            else:
                median_val = median(values)

            query = cursor.mogrify(sql.SQL('UPDATE {}.{} SET {}= %s WHERE {} IS NULL;').format(
                sql.Identifier(schema_name),
                sql.Identifier(table),
                sql.Identifier(column),
                sql.Identifier(column)
            ), (median_val,))
            cursor.execute(query)
            self.dbconnect.commit()
        except Exception as e:
            app.logger.error("[ERROR] Unable to impute missing data for column {} by median".format(column))
            app.logger.exception(e)
            self.dbconnect.rollback()
            raise e

    def impute_missing_data(self, schema_id, table, column, function):
        """" impute missing data based on the average"""

        if function == "AVG":
            return self.impute_missing_data_on_average(schema_id, table, column)
        elif function == "MEDIAN":
            return self.impute_missing_data_on_median(schema_id, table, column)
        else:
            app.logger.error("[ERROR] Unable to impute missing data for column {}".format(column))


class DateTimeTransformer:
    def __init__(self, dbconnection):
        self.dbconnect = dbconnection

    def extract_element_from_date(self, schema_id, table, column, element):
        """" Return element of date out of timestamp"""
        try:
            schema_name = 'schema-' + str(schema_id)
            new_column = column + ' (' + element + ')'
            cursor = self.dbconnect.get_cursor()
            data_loader = DataLoader(self.dbconnect)
            data_loader.insert_column(schema_id, table, new_column, "double precision")
            query = cursor.mogrify(
                sql.SQL(' UPDATE {}.{} SET {} = (EXTRACT(' + element + ' FROM {}::TIMESTAMP));').format(
                    sql.Identifier(schema_name),
                    sql.Identifier(table),
                    sql.Identifier(new_column),
                    sql.Identifier(column)))
            cursor.execute(query)
            self.dbconnect.commit()
        except Exception as e:
            app.logger.error("[ERROR] Unable to extract " + element + " from column '{}'".format(column))
            app.logger.exception(e)
            self.dbconnect.rollback()
            raise e

        # Log action to history
        history = History(self.dbconnect)
        history.log_action(schema_id, table, datetime.now(), 'Extracted ' + element + ' from column ' + column)

    def extract_time_or_date(self, schema_id, table, column, element):
        """extract date or time from datetime type"""
        try:
            schema_name = 'schema-' + str(schema_id)
            new_column = column + ' (' + element + ')'
            cursor = self.dbconnect.get_cursor()
            data_loader = DataLoader(self.dbconnect)
            data_loader.insert_column(schema_id, table, new_column, element)
            query = cursor.mogrify(
                sql.SQL('UPDATE {}.{} SET {} = {}::' + element.lower() + ';').format(
                    sql.Identifier(schema_name),
                    sql.Identifier(table),
                    sql.Identifier(new_column),
                    sql.Identifier(column)))
            cursor.execute(query)
            self.dbconnect.commit()
        except Exception as e:
            app.logger.error("[ERROR] Unable to extract " + element + " from column '{}'".format(column))
            app.logger.exception(e)
            self.dbconnect.rollback()
            raise e

        # Log action to history
        history = History(self.dbconnect)
        history.log_action(schema_id, table, datetime.now(), 'Extracted ' + element + ' from column ' + column)

    def get_transformations(self):
        trans = ["extract day of week", "extract month", "extract year", "parse date", "extract time", "extract date"]
        return trans

    def transform(self, schema_id, table, column, operation):
        if operation == "extract day of week":
            return self.extract_element_from_date(schema_id, table, column, "DOW")
        elif operation == "extract month":
            return self.extract_element_from_date(schema_id, table, column, "MONTH")
        elif operation == "extract year":
            return self.extract_element_from_date(schema_id, table, column, "YEAR")
        elif operation == "extract date":
            return self.extract_time_or_date(schema_id, table, column, "DATE")
        elif operation == "extract time":
            return self.extract_time_or_date(schema_id, table, column, "TIME")


class NumericalTransformations:
    def __init__(self):
        pass

    def normalize(self, schema_id, table_name, column_name):
        schema_name = 'schema-' + str(schema_id)
        df = pd.read_sql_query('SELECT * FROM "{}"."{}"'.format(schema_name, table_name), db.engine)
        new_column_name = column_name + '_norm'

        df[new_column_name] = df[column_name]
        if df[column_name].std(ddof=0):
            df[new_column_name] = (df[column_name] - df[column_name].mean()) / df[column_name].std(ddof=0)

        db.engine.execute('DROP TABLE "{0}"."{1}"'.format(schema_name, table_name))
        df.to_sql(name=table_name, con=db.engine, schema=schema_name, if_exists='fail', index=False)

    def equal_width_interval(self, schema_id, table_name, column_name, num_intervals):
        schema_name = 'schema-' + str(schema_id)
        df = pd.read_sql_query('SELECT * FROM "{}"."{}"'.format(schema_name, table_name), db.engine)
        new_column_name = column_name + '_intervals_eq_w_' + str(num_intervals)

        df[new_column_name] = pd.cut(df[column_name], num_intervals).apply(str)

        db.engine.execute('DROP TABLE "{0}"."{1}"'.format(schema_name, table_name))
        df.to_sql(name=table_name, con=db.engine, schema=schema_name, if_exists='fail', index=False)

    def equal_freq_interval(self, schema_id, table_name, column_name, num_intervals):
        schema_name = 'schema-' + str(schema_id)
        df = pd.read_sql_query('SELECT * FROM "{}"."{}"'.format(schema_name, table_name), db.engine)
        new_column_name = column_name + '_intervals_eq_f_' + str(num_intervals)

        sorted_data = list(df[column_name].sort_values())
        data_length = len(df[column_name])
        interval_size = data_length // num_intervals
        intervals_list = []
        for i in range(0, data_length, interval_size):
            intervals_list.append(sorted_data[i])
        df[new_column_name] = pd.cut(df[column_name], intervals_list)

        db.engine.execute('DROP TABLE "{0}"."{1}"'.format(schema_name, table_name))
        df.to_sql(name=table_name, con=db.engine, schema=schema_name, if_exists='fail', index=False)

    def manual_interval(self, schema_id, table_name, column_name, intervals):
        schema_name = 'schema-' + str(schema_id)
        df = pd.read_sql_query('SELECT * FROM "{}"."{}"'.format(schema_name, table_name), db.engine)
        new_column_name = column_name + 'intervals_custom'

        df[new_column_name] = pd.cut(df[column_name], intervals).apply(str)

        db.engine.execute('DROP TABLE "{0}"."{1}"'.format(schema_name, table_name))
        df.to_sql(name=table_name, con=db.engine, schema=schema_name, if_exists='fail', index=False)

    def remove_outlier(self, schema_id, table_name, column_name, value, less_than=False):
        schema_name = 'schema-' + str(schema_id)
        if less_than:
            db.engine.execute(
                'DELETE FROM "{0}"."{1}" WHERE "{1}" < {2}'.format(schema_name, table_name, column_name, value))
        else:
            db.engine.execute(
                'DELETE FROM "{0}"."{1}" WHERE "{1}" > {2}'.format(schema_name, table_name, column_name, value))
