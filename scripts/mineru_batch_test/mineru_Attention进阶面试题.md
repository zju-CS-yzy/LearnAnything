## 1 传统 Attention 存在哪些问题？

1. 传统 Attention 存在 上下文长度 约束问题；

2. 传统 Attention 速度慢，内存占用大；

## 2 Attention 优化方向

1. 提升上下文长度

2. 加速、减少内存占用

## 3 Attention 变体有哪些？

• 稀疏 attention。将稀疏偏差引入 attention 机制可以降低了复杂性；

• 线性化 attention。解开 attention 矩阵与内核特征图，然后以相反的顺序计算 attention 以实现线性复杂度；

• 原型和内存压缩。这类方法减少了查询或键值记忆对的数量，以减少注意力矩阵的大小；

• 低阶 self-Attention。这一系列工作捕获了 self-Attention 的低阶属性；

• Attention 与先验。该研究探索了用先验 attention 分布来补充或替代标准 attention；

• 改进多头机制。该系列研究探索了不同的替代多头机制。

## 4 Multi-Query Attention 篇

## 4.1 Multi-head Attention 存在什么问题？

• 训练过程：不会显著影响训练过程，训练速度不变，会引起非常细微的模型效果损失；

• 推理过程：反复加载 巨大 的 KV cache , 导致 内存开销大，性能是内存受限；

## 4.2 介绍一下 Multi-Query Attention？

Multi-Query Attention 在所有注意力头上 共享 key 和 value.

![](images/4acba349efc96e163a4eb69cc9bbd7d65fee0c16ae60d32f7f81ffbeccb7c67c.jpg)

## 4.3 对比一下 Multi-head Attention 和 Multi-Query Attention？

• Multi-head Attention：每个注意力头都有各自的query、key和value。

• Multi-query Attention: 在所有的注意力头上共享key和value。

<table><tr><td>模型</td><td>n_heads</td><td>head_dim</td><td>FFN中间维度</td><td>维度h</td></tr><tr><td>LLaMA</td><td>32</td><td>128</td><td>11008</td><td>4096</td></tr><tr><td>baichuan</td><td>32</td><td>128</td><td>11008</td><td>4096</td></tr><tr><td>ChatGLM-6B</td><td>32</td><td>128</td><td>4h, 16384</td><td>4096</td></tr><tr><td>ChatGLM2-6B</td><td>32</td><td>128</td><td>13696</td><td>4096</td></tr><tr><td>Bloom</td><td>32</td><td>128</td><td>4h, 16384</td><td>4096</td></tr><tr><td>Falcon</td><td>71</td><td>64</td><td>4h, 18176</td><td>4544</td></tr></table>

Falcon、PaLM、ChatGLM2-6B都使用了Multi-query Attention，但有细微差别。

• 为了保持参数量一致，

• Falcon: 把隐藏维度从4096增大到了4544。多余的参数量分给了Attention块和FFN块

• ChatGLM2: 把FFN中间维度从11008增大到了13696。多余的参数分给了FFN块

## 4.4 Multi-Query Attention 这样做的好处是什么？

减少 KV cache 的大小，减少显存占用，提升推理速度。

## 4.5 有 哪些模型 是 使用 Multi-Query Attention？

• 代表模型：PaLM、ChatGLM2、Falcon等

5 Grouped-query Attention

## 5.1 什么是 Grouped-query Attention？

Grouped query attention: 介于multi head和multi query之间，多个key和value。

## 5.2 有哪些大模型使用 Grouped-query Attention？

ChatGLM2，LLaMA2-34B/70B使用了Grouped query attention。

## 6 FlashAttention

• 核心：用分块softmax等价替代传统softmax

• 优点：节约HBM，高效利用SRAM，省显存，提速度

• 代表模型：Meta推出的开源大模型LLaMA，阿联酋推出的开源大模型Falcon都使用了Flash Attention来加速计算和节省显存

• 关键词：HBM、SRAM、分块Softmax、重计算、Kernel融合。

## 7 并行 transformer block

用并行公式替换了串行，提升了15%的训练速度。

在8B参数量规模，会有轻微的模型效果损失;在62B参数量规模，就不会损失模型效果。

Falcon、PaLM都使用了该技术来加速训练

![](images/5b9bc5db35c5a610be1f398e9e70376433c9b39395b262b1844672ff2262770e.jpg)  
(1) GPT Block

![](images/b3e02e7aa379e294b5d66594541c0c3197296113fe45a7a50b9f4197cd7fb74c.jpg)  
(2) LLaMA Block

![](images/4a7f5ea3191375460f173ff5c5d3d16ac8421be2d678b5465dde72a746debbf7.jpg)  
(3) Falcon Block