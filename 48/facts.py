# coding:utf-8
# 多因子选股, 用机器学习算法


import backtrader as bt
import backtrader.indicators as bi
import backtest
import pandas as pd
import os
import tushare as ts
import matplotlib.pyplot as plt
from xpinyin import Pinyin
import datetime
import random
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn import metrics
from sklearn.externals import joblib
import numpy as np
# from sklearn.preprocessing import OneHotEncoder
import seaborn as sns


# 获取股票数据，进行初步筛选，返回供因子分析的股票数据。
def getFactors():
#    data = ts.get_stock_basics()
#    print(data.head())
#    print(len(data))
#    data.to_csv("stocks.csv")
    data = pd.read_csv("stocks.csv", index_col = "code")
    # 排除亏损的股票
    data = data[data.npr > 0.0]
    # 排除上市不满2年的
    data = data[data.timeToMarket <= 20180801]
    # 排除ST股票
    data = data[~ data.name.str.contains("ST")]
    # 排除代码小于100000的股票
    data = data[data.index >= 100000]
    # 排除退市的股票
    data = data[data.pe != 0]
    return data
    
    
# 根据股票代码找股票名称
def fromCodeToName(factors, codes):
    # 准备数据
    name = factors[factors.index.isin(codes)].name.values
    # 将汉字转换为拼音
    p = Pinyin()
    names = [p.get_pinyin(s) for s in name]
    return names
        
    
# 对所有股票回测其年化收益率
def getReturn(data):
    if os.path.exists("data.csv"):
        data = pd.read_csv("data.csv", index_col = "code")
        return data
    start = "2017-01-01"
    end = "2020-07-31"
    codes = data.index
    names = fromCodeToName(data, codes)
    codes = [str(x) for x in codes]
#    print(codes)
#    print(names)
    # 在数据中增加一列计算年化收益率
    data["ar"] = 0.0
    t = 0
    cash = 100000
    for code in data.index:
        test = backtest.BackTest(FactorStrategy, start, end, [str(code)], [names[t]], cash, bDraw = False)
        result = test.run()
        print("第{}次回测，股票代码{}，回测年化收益率{}。".format(t+1, code, result.年化收益率))
        data.loc[code, ["ar"]] = result.年化收益率
        t += 1
    data.to_csv("data.csv")
    return data


# 分析数据
def analysis(data):
    print(data.info())
    # 收益率分布情况
    plt.figure()
    data.ar.hist(bins = 100)
    plt.savefig("returns.png")
    plt.close()
    print(data.ar.max())
    # 画图看各数据关系。
    # g = sns.pairplot(data)
    # g.savefig("data.png")
    
    
# 多元线性回归
def multiRegress(data):
    x = data.iloc[:, 3:21]
    y = data.iloc[:, 22]
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size = 0.2, random_state = 631)
    line_reg = LinearRegression()
    model = line_reg.fit(x_train, y_train)
    print("模型参数:", model)
    print("模型截距:", model.intercept_)
    print("参数权重:", model.coef_)
    
    y_pred = line_reg.predict(x_test)
    sum_mean = 0
    for i in range(len(y_pred)):
        sum_mean += (y_pred[i] - y_test.values[i]) ** 2
    sum_erro = np.sqrt(sum_mean /len(y_pred))
    print("RMSR=", sum_erro)
    print("Score=", model.score(x_test, y_test))
    # ROC曲线
    plt.figure()
    plt.plot(range(len(y_pred)), y_pred, 'b', label="predict")
    plt.plot(range(len(y_pred)), y_test, 'r', label="test")
    plt.legend(loc="upper right") 
    # 显示图中的标签
    plt.xlabel("facts")
    plt.ylabel('ar')
    plt.savefig("line_regress_result.png")
    plt.close()
    # 保存模型
    joblib.dump(model, "LineRegress.m")
    return model
    
    
# 测试多元线性回归的效果
def testMultiRegress(data):
    model = joblib.load("LineRegress.m")
    pred_return = model.predict(data.iloc[:, 3:21])
    # print(pred_return)
    data["pred_ar"] = pred_return
    # print(data)
    # 排序
    data = data.sort_values(by = "pred_ar", ascending = False)
    # print(data)
    # 取前十个股票作为投资标的
    codes = data.index[0:10].values
    # print(codes)
    names = fromCodeToName(data, codes)
    codes = [str(x) for x in codes]
    start = "2010-01-01"
    end = "2020-07-01"
    cash = 1000000
    opttest = backtest.BackTest(FactorStrategy, start, end, codes, names, cash, bDraw = True)
    result = opttest.run()
    print("多元线性回归的回测结果:")
    print(result)
    
    
# 计算评分指标
def scale(factors, a1=1.0, a2 = 1.0, a3 = 1.0, a4 = 1.0, a5 = 1.0):
    pe = -1.0*a1*factors.pe/factors.pe.mean()
    esp = a2*factors.esp/factors.esp.mean()
    bvps = a3*factors.bvps/factors.bvps.mean()
    pb = a4*factors.pb/factors.pb.mean()
    npr = a5*factors.npr/factors.npr.mean()
    score = pe+esp+bvps+pb+npr
    # print(score)
    # 排序并画图
    score = score.sort_values()
    # print(score)
    # score.plot(kind = "hist", bins = 1000, range = (-25.0, 30.0))
    # plt.savefig("fsctorScore.png")
    return score
    
    
# 交易策略类，一开始买入然后持有。
class FactorStrategy(bt.Strategy):
    def __init__(self):
        self.p_value = self.broker.getvalue()*0.9/10.0
        self.bOutput = False
        
    def next(self):
        # 买入
        for data in self.datas:
            # 获取仓位
            pos = self.getposition(data).size
            if pos == 0:
                size = int(self.p_value/100/data.close[0])*100
                self.buy(data = data, size = size)
        # 最后卖出
        date = self.datas[0].datetime.date(0)
        closeDate = datetime.datetime(2020, 7, 31)
        if date.year == closeDate.year and date.month == closeDate.month and date.day == closeDate.day:
            for data in self.datas:
                pos = self.getposition(data).size
                if pos != 0:
                    self.sell(data = data, size = pos )
                
    # 输出
    def log(self, txt):
        print(txt)
        
    # 输出交易过程
    def __displayOrder(self, buy, order):
        if buy:
            self.log(
                    '执行买入, 价格: %.2f, 成本: %.2f, 手续费 %.2f' %
                    (order.executed.price,
                     order.executed.value,
                     order.executed.comm))
        else:
            self.log(
                    '执行卖出, 价格: %.2f, 成本: %.2f, 手续费 %.2f' %
                    (order.executed.price,
                     order.executed.value,
                     order.executed.comm))
                
    # 交易情况
    def notify_order(self, order):
        if self.bOutput == False:
            return
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status in [order.Completed]:
            if order.isbuy():
                self.__displayOrder(True, order)
            elif order.issell():
                self.__displayOrder(False, order)
        self.order = None
        
    

        
        
# 实际做回测的函数
def doBacktest(factors, strategy, a1, a2, a3, a4, a5, start, end, cash):
    score = scale(factors, a1, a2, a3, a4, a5)
    codes = score[-10:].index
    name = fromCodeToName(factors, codes)
    code = [str(x) for x in codes]
    opttest = backtest.BackTest(strategy, start, end, code, name, cash, bDraw = False)
    result = opttest.run()
    return result, code
        
        
# 对不同的因子权重组合进行优化
def optStrategy(factors, strategy, cash = 1000000, bDraw = False):
    start = "2018-01-01"
    end = "2020-07-05"

    res = []
    maxRes = 0.0
    maxParams = [0, 0, 0, 0, 0]
    x = 200
    step = 100
    for a1 in range(1, x, step):
        for a2 in range(1, x, step):
            for a3 in range(1, x, step):
                for a4 in range(1, x, step):
                    for a5 in range(1, x, step):
                        result, code = doBacktest(factors, strategy, a1, a2, a3, a4, a5, start, end, cash)
                        print("a1 = {}, a2 = {}, a3 = {}, a4 = {}, a5 = {}, 年化收益率: {}\n".format(a1, a2, a3, a4, a5, result.年化收益率))
                        res.append(result.年化收益率)
                        if result.年化收益率 > maxRes:
                            maxRes = result.年化收益率
                            maxParams = [a1, a2, a3, a4, a5]
    print("最佳权重:", maxParams, "最大年化收益率:", maxRes)
    return res
    
    
# 采用随机算法进行优化
def randOpt(factors, strategy, times = 200, cash = 1000000, bDraw = False):
    start = "2018-01-01"
    end = "2020-07-05"

    # 记录结果用来进行进一步分析
    data = pd.DataFrame()
    res = []
    maxRes = 0.0
    maxParams = [0, 0, 0, 0, 0]
    random.seed()
    for i in range(times):
        a1 = random.randint(1, 200)
        a2 = random.randint(1, 200)
        a3 = random.randint(1, 200)
        a4 = random.randint(1, 200)
        a5 = random.randint(1, 200)
        result, code = doBacktest(factors, strategy, a1, a2, a3, a4, a5, start, end, cash)
        print("第{}次尝试:a1 = {}, a2 = {}, a3 = {}, a4 = {}, a5 = {}, 年化收益率: {}\n".format(i+1, a1, a2, a3, a4, a5, result.年化收益率))
        
        res.append(result.年化收益率)
        data = data.append(pd.DataFrame({"a1":[a1], "a2":[a2], "a3":[a3], "a4":[a4], "a5":[a5], "result":[result.年化收益率]}), ignore_index = True)
        if result.年化收益率 > maxRes:
            maxRes = result.年化收益率
            maxParams = [a1, a2, a3, a4, a5]
    print("最佳权重:", maxParams, "最大年化收益率:", maxRes)
    # data.reset_index(drop = True)
    data.to_csv("factor_result.csv")
    return res
    
    
# 绘图
def draw(data, filename):
    plt.figure()
    plt.tight_layout()
    plt.subplots_adjust(wspace = 0.5, hspace = 0.5)
    plt.subplot(231)
    plt.plot(data.a1, data.result, "bo")
    plt.xlabel("pe")
    plt.ylabel("ar")
    plt.subplot(232)
    plt.plot(data.a2, data.result, "bo")
    plt.xlabel("esp")
    plt.ylabel("ar")
    plt.subplot(233)
    plt.plot(data.a3, data.result, "bo")
    plt.xlabel("bvps")
    plt.ylabel("ar")
    plt.subplot(234)
    plt.plot(data.a4, data.result, "bo")
    plt.xlabel("pb")
    plt.ylabel("ar")
    plt.subplot(235)
    plt.plot(data.a5, data.result, "bo")
    plt.xlabel("npr")
    plt.ylabel("ar")
    plt.savefig(filename)
    
# 回归分析
def regress(data):
    print(data)
    draw(data, "factor_analysis.png")
    # 剔除年化收益率在0.1-0.2之间的数据
    data = data[data.result > 0.2]
    draw(data, "factor_after_clean.png")
    # 进行多元线性回归
    # 划分数据
    print(data.describe())
    X = data.loc[:, ["a1", "a2", "a3", "a4", "a5"]]
    Y = data.loc[:, ["result"]]
    # print("测试")
    # print(X, Y)
    X_train, X_test, Y_train, Y_test = train_test_split(X, Y, test_size = 0.25, random_state = 1)
    print(X_test, Y_test)
    # 建模
    model = LinearRegression()
    model.fit(X_train, Y_train)
    predictions = model.predict(X_test)
    cha = []
    for i, prediction in enumerate(predictions):
        print("预测值:%s, 目标值:%s" % (prediction, Y_test.iloc[i, :]))
        cha.append(prediction - Y_test.iloc[i, :])
    print("R平方值:%.2f" % model.score(X_test, Y_test))
    MSE = metrics.mean_squared_error(Y_test, predictions)
    RMSE = np.sqrt(MSE)
    print("MSE:", MSE)
    print("RMSE:", RMSE)
    # 画图看看
    plt.figure(figsize=(15,5))
    plt.plot(range(len(Y_test)), Y_test, 'r',    label='test data')
    plt.plot(range(len(Y_test)), predictions, 'b', label='predict data')
    plt.legend()
    plt.savefig("因子选股线性回归结果.png")
    plt.figure()
    plt.scatter(Y_test, predictions)
    plt.plot([Y_test.min(),Y_test.max()], [Y_test.min(),Y_test.max()], 'k--')
    plt.xlabel('real value')
    plt.ylabel('predict value')
    plt.savefig("因子选股线性回归结果(散点图).png")
    # 画残差图
    plt.figure()
    plt.scatter(range(len(Y_test)), cha)
    plt.ylabel("cha")
    plt.savefig("因子选股线性回归残差图.png")
    # 保存模型
    joblib.dump(model, "Regress.m")
    return model
    
    
# 用线性回归所得模型选择因子权重
def regressChoose(factors, strategy, model, times = 200, cash = 1000000, bDraw = False):
    start = "2018-01-01"
    end = "2020-07-05"

    random.seed()
    best  = 0.0
    bestWeight = [0, 0, 0, 0, 0]
    data = pd.DataFrame()
    N = 200
    for i in range(times):
        a1 = random.randint(1, N)
        a2 = random.randint(1, N)
        a3 = random.randint(1, N)
        a4 = random.randint(1, N)
        a5 = random.randint(1, N)
        data = data.append(pd.DataFrame({"a1":[a1], "a2":[a2], "a3":[a3], "a4":[a4], "a5":[a5]}), ignore_index = True)
    # print(data)
    pred = model.predict(data)
    best = pred.max()
    bestPos = np.argmax(pred)
    bestWeight = [data.iloc[bestPos, 0], data.iloc[bestPos, 1], data.iloc[bestPos, 2], data.iloc[bestPos, 3], data.iloc[bestPos, 4]]
    result, code = doBacktest(factors, strategy, bestWeight[0], bestWeight[1], bestWeight[2], bestWeight[3], bestWeight[4], start, end, cash)
    print("模型预测年化收益率{}, 实际回测年化收益率: {}\n".format(best, result.年化收益率)) 
    return code
    
    
# 根据输入的股票池进行回测检验
def checkResult(strategy, codes, names, start, end, cash = 1000000):
    opttest = backtest.BackTest(strategy, start, end, codes, names, cash)
    result = opttest.run()
    print("回测结果")
    print(result)
    

if __name__ == "__main__":
    factors = getFactors()
    # 进行回测,获取各只股票的年化收益率
    data = getReturn(factors)
    # 数据分析
    analysis(data)
    # 进行多元线性回归分析
    multiRegress(data)
    # 回测多元线性回归的结果
    testMultiRegress(data)
#    name = factors.loc[codes, "name"].values
    # 将汉字转换为拼音
#    p = Pinyin()
#    name = [p.get_pinyin(s) for s in name]
#    code = [str(x) for x in codes]
#    # print(len(name), code)
#    backtest = backtest.BackTest(FactorStrategy, start, end, code, name, 1000000, bDraw = True)
#    result = backtest.run()
    # backtest.output()
#    print(result)
    #res = optStrategy(factors, FactorStrategy)
#    print(res)
#    plt.figure()
#    plt.hist(res)
#    plt.savefig("factor_res.png")
    # 随机算法
    # res = randOpt(factors, FactorStrategy, times = 8000)
    # print(res)
    # plt.figure()
    # plt.hist(res)
    # plt.savefig("factor_res.png")
    # 回归分析
#    data = pd.read_csv("factor_result.csv", index_col = 0)
#    model = regress(data)
#    # 用回归分析的结果进行回测
#    model = joblib.load("Regress.m")
#    bestResult = regressChoose(factors, FactorStrategy, model, times = 10000)
#    print("股票池为:", bestResult)
#    start = "2010-01-01"
#    end = "2020-07-05"
#    name = fromCodeToName(factors, bestResult)
#    checkResult(FactorStrategy, bestResult, name, start, end)
#    
