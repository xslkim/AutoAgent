# IL2CPP 配置指南（给接入 AutoAgent 的游戏项目）

> 面向**用户的游戏项目** —— 你把 AutoAgent adapter 接进自己的 Unity 工程、并用
> IL2CPP backend 出包时该注意什么。AutoAgent adapter 自身的防裁剪已经处理好了
> （见下方 §2），本文重点是**你自己的业务代码**。

---

## 1. 背景：IL2CPP 会裁掉"看起来没用"的代码

用 IL2CPP scripting backend 出包时，Unity 的 **managed bytecode stripper** 会删掉
它静态分析认为"没被引用"的类型和方法。问题在于：**通过反射、序列化、JSON 反序列化
等间接方式调用的代码，stripper 看不到**，于是被误删 —— 运行时报
`MissingMethodException` / `NullReferenceException` 或行为异常。

解决办法是 **`link.xml`**：一个告诉 stripper "这些别删" 的清单文件。Unity 会自动
拾取项目里**任何根元素是 `<linker>` 的 `.xml` 文件**。

---

## 2. AutoAgent adapter 自身 —— 已处理，无需你操心

adapter 包内置了 `adapters/unity/Runtime/Resources/AutoAgent.link.xml`，把整个
`AutoAgent.Runtime` 程序集 `preserve="all"`。adapter 由 Unity 生命周期钩子启动、
靠 WebSocket JSON-RPC 循环分发 wire 方法，部分入口是间接到达的，所以整体保留。

你**不需要**为 adapter 再写 link.xml。

---

## 3. 你的业务代码 —— 可能需要自己的 link.xml

如果你的游戏代码有下列情况，IL2CPP 出包后可能被裁出问题：

- 用 `Type.GetType("...")` / `Activator.CreateInstance` 按名字反射构造类型
- 用 `JsonUtility` / Newtonsoft.Json / `MessagePack` 等反序列化到自定义类
- 自定义 `MonoBehaviour` 仅由场景 / prefab 引用，且类名被改过
- 用 `SendMessage` / `Invoke("方法名")` 按字符串调用方法

### 怎么做

在 `Assets/` 下任意位置放一个 `link.xml`（文件名建议带项目前缀避免冲突，例如
`MyGame.link.xml`），内容示例：

```xml
<linker>
  <!-- 保留整个程序集（最省事，代价是包略大） -->
  <assembly fullname="MyGame.Runtime" preserve="all" />

  <!-- 或者只保留特定类型 / 命名空间，更精细 -->
  <assembly fullname="MyGame.Core">
    <type fullname="MyGame.Core.SaveData" preserve="all" />
    <namespace fullname="MyGame.Core.Dto" preserve="all" />
  </assembly>
</linker>
```

`fullname` 用程序集名（不带 `.dll`）。没有 asmdef 的脚本默认在
`Assembly-CSharp` 程序集里。

### 验证

1. **Project Settings → Player → Other Settings → Managed Stripping Level** 调到
   `High`（最容易暴露裁剪问题）。
2. 出 IL2CPP 包，跑通你依赖反射的功能。
3. 没报 `MissingMethodException` 之类即可。

> 经验：先用 `preserve="all"` 整程序集保留把包跑通，再按需收窄到具体类型。

---

## 4. CI 里的 IL2CPP 校验

AutoAgent 仓库的 `unity-pr.yml` 有一个 `il2cpp-build` job：改动 Unity adapter 的
PR 会在 self-hosted runner 上跑一次 Win64 IL2CPP 出包，确认 adapter 在 IL2CPP
下能正常 build。该 job 依赖 runner 装了 Unity 的 **Windows IL2CPP build support**
模块。
