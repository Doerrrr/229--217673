# CLIFFORD-POSTSELECT v02：中途投影、记录概率与条件复振幅

实现 `/work/bench` 中 `./bin/analyze --input input.json --output result.jsonl`。从全零计算基态开始，电路既有Clifford酉门，也有指定结果的中途计算基测量。求该整条测量记录的发生概率，以及条件于该记录成功时最终基态的精确复振幅和概率。保留全局相位，不能把中途投影移动到电路末尾。

## 输入与门

UTF-8 JSON可带BOM，顶层键恰为version、queries。version为整数1，queries含1—16个id唯一对象。拒绝重复JSON键、NaN/Infinity、缺失或未知字段，布尔值不是整数。id为1—64个ASCII字母、数字、下划线或连字符。

query键恰为id、n、gates、targets。n为1—64整数；gates含0—512个门，按列表次序作用，H门最多96个、POST门最多32个。单线酉门键恰为gate、q，gate属于H、S、SDG、X、Y、Z，q为0…n−1整数；双线门键恰为gate、a、b，gate属于CX、CZ、SWAP，a、b为不同的0…n−1整数。POST门键恰为gate、q、outcome，outcome为0或1的JSON整数。targets含1—8个不同的长度n的01字符串，从左到右表示q0、q1、…、q(n−1)。

初态|00…0>振幅为1，其他为0，状态是列向量。

- H=(1/sqrt(2))*[[1,1],[1,−1]]；S=diag(1,i)；SDG=diag(1,−i)。
- X=[[0,1],[1,0]]；Y=[[0,−i],[i,0]]；Z=diag(1,−1)。特别是Y|0>=i|1>、Y|1>=−i|0>。
- CX以a控制b；CZ仅当两线均1时乘−1；SWAP交换两线。
- POST(q,b)是投影|b><b|：把该线不等于b的所有振幅设为0，其他振幅保持，不额外翻转、重置或施加相位。后续门继续作用于这条线。

按完整门序列求得**未归一化**向量phi。success=P=sum_x |phi_x|²是整条POST记录的联合发生概率。若P>0，条件向量psi=phi/sqrt(P)，sqrt(P)取正实数；要求输出psi的振幅及|psi_x|²。没有POST时P=1。若P=0，条件态不存在，本题约定所有被查询振幅和条件概率均输出精确0，并将success输出0；这属于正常求解结果。

## 精确输出

JSONL与queries同序，每行键恰为id、state、result。完整state=SOLVED，result键恰为success、amplitudes、probabilities。

success为精确有理数字符串。amplitudes和probabilities长度均等于targets长度。每个振幅键恰为real、imag，各为两个有理数字符串[a,b]，表示a+b*sqrt(2)。因此完整振幅为(real[0]+real[1]*sqrt(2))+i*(imag[0]+imag[1]*sqrt(2))。probabilities为各目标的条件测量概率，P=0时按上面的约定。

有理字符串允许ASCII正负号、十进制整数、可选/及严格正整数分母，允许未约分分数；不接受空白、小数或指数。此门集合下P和条件基态概率均为有理数，条件振幅可在上述数域中精确表示。全部查询只涉及部分基态，所列条件概率无需和为1。

未交结果可UNSOLVED且result=null。只输出归一化概率、稳定子射线或忽略记录发生概率均不足以完成题目。多个程序只差全局相位时，本题仍按矩阵和正平方根规定分别验收其复振幅。

示例：n=1，门为H、POST(q0,0)、Y，最终记录概率success=1/2，条件态为i|1>。targets=["0","1"]时振幅为0和i，条件概率为0、1。若把POST结果改为1，则最终条件态为−i|0>。n=1，门X、POST(q0,0)时记录不可能，success及全部输出均0。

## 工程、资源和评分

两CLI参数必填，先完整校验输入。格式错误、缺参数或不可读输入时非零退出、stderr非空、stdout为空，旧输出原字节不变。正常退出0、stdout为空，建立多层输出父目录，完整临时文件写成后原子替换；写失败非零退出。

固定2CPU、2048MiB，单次300秒。已有科学计算库、编译工具可用，允许查公开资料、自测，不限定表示或算法。完整合法域包括无法直接展开2^n个复数的电路；需管理内存和时间，正常表达未解决查询，不能以挂起或崩溃表示不会。修改app/、bin/，必要时build.sh，无需嵌套Docker。

条件复振幅0.60、整条记录的联合发生概率0.15、条件基态概率0.15、工程保护与批量顺序0.10。各组按实例比例，无额外封顶。三组数学条件分别精确验收，不使用浮点容差或采样估计；不同但相等的有理表达均接受。超时、信号或验证异常不算有效低分。
