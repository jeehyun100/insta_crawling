import pandas as pd
import datetime


class pandas_utils(object):
    def __init__(self):
        return print("init class")
    def make_df(self):
        data1 = [['A',1],['B',2],['C',3]]
        data2 = [['E', 1], ['F', 2], ['C', 2]]

        df1 = pd.DataFrame(data1, columns=['id', 'ModifyDatetime'])
        df2 = pd.DataFrame(data2, columns=['id', 'ModifyDatetime'])
        return df1, df2
    def save_df(self):
        return None

    def merge(self, df1, df2):
        result = pd.merge(df1, df2, how='outer', on=['id'])
        #df['period'] = df[['Year', 'quarter']].apply(lambda x: ''.join(x), axis=1)
        # def my_test2(row):
        #     ....:
        #     return row['a'] % row['c']
        #df['Value'] = df.apply(my_test2, axis=1)
        result = result.fillna(0)
        #result.columns = columns_name
        result = result.apply(self.compare_modify_time2, axis=1)

        #Column Rename for crowling time
        result = result.rename(columns={'Crawling_time_x': 'Crawling_time','Total_post_x':'Total_post'})

        return result

    def compare_modify_time2(self, row):
        _original_time = row['ModifyDatetime_x']
        modify_time = row['ModifyDatetime_y']
        try:
            original_time = datetime.datetime.strptime(_original_time, "%Y-%m-%d %H:%M:%S")
        except Exception:
            original_time = datetime.datetime.strptime('1900-01-01 00:00:00', "%Y-%m-%d %H:%M:%S")

        if original_time  < modify_time:
            actual_time = modify_time
            active_flag = 'Y'
        else:
            actual_time = original_time
            active_flag = 'N'

        row["ModifyDatetime"] = actual_time.strftime("%Y-%m-%d %H:%M:%S")
        row["ActiveFlag"] = active_flag
        return row



def main():
    pd_utils = pandas_utils()
    pd1, pd2 = pd_utils.make_df()
    merge_df = pd_utils.merge(pd1, pd2)

    print(merge_df)

if __name__ == "__main__":

    main()
