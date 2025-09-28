import olca                       # 不同版本情况下olca包的导入方式不一样
#import olca_ipc as ipc           # 负责 IPC 通信
import olca_schema as o             # 完整数据模型
import time
import olca_schema.schema as S

from olca_schema import (           # 直接导入常用类/枚举
    CalculationSetup,
    # CalculationType,                # 移除这行 - 新版本中不存在
    Ref,
    RefType,
)

PORT = 8080                         # 按实际端口修改

try:
    client = olca.Client(PORT)
    #client = ipc.Client(PORT)
    # 检查连接 - 移除 get_server_info() 调用
    print("正在连接到 openLCA...")
    print("已连接到 openLCA")
    
    # 1) 获取流程与影响方法
    print("正在查找流程和影响评估方法...")
    
    # 查找钢铁生产流程
    steel = client.find(o.Process, name="electric cables")
    if not steel:
        print("未找到 'electric cables' 流程，尝试查找其他相关流程...")
        # 尝试查找包含 steel 的流程
        processes = client.get_all(o.Process)
        steel_processes = [p for p in processes if 'electric' in p.name.lower()]
        if steel_processes:
            steel = steel_processes[0]
            print(f"找到流程: {steel.name}")
        else:
            raise Exception("未找到任何相关流程")
    else:
        print(f"找到流程: {steel.name}")
    
    # 使用 ILCD 2016 midpoint 方法
    method = client.find(o.ImpactMethod, name="ILCD 1.0.8 2016 midpoint")
    if not method:
        print("未找到 'ILCD 1.0.8 2016 midpoint' 方法，尝试查找其他方法...")
        # 尝试查找包含 ILCD 的方法
        methods = client.get_all(o.ImpactMethod)
        ilcd_methods = [m for m in methods if 'ilcd' in m.name.lower() or '2016' in m.name]
        if ilcd_methods:
            method = ilcd_methods[0]
            print(f"找到影响评估方法: {method.name}")
        else:
            # 如果没有找到 ILCD，尝试其他方法
            if methods:
                method = methods[0]
                print(f"使用备用方法: {method.name}")
            else:
                raise Exception("未找到任何影响评估方法")
    else:
        print(f"找到影响评估方法: {method.name}")

    # 2) 构建计算设置
    print("正在设置计算参数...")
    setup = CalculationSetup(
        # calculation_type = CalculationType.UPSTREAM_ANALYSIS,  # 移除这行
        amount           = 1.0,
        target           = Ref(ref_type=RefType.Process,       id=steel.id),
        impact_method    = Ref(ref_type=RefType.ImpactMethod,  id=method.id),
        
    )
    simulator=client.simulate(setup)
    

    # 3) 运行并等待完成
    print("正在运行计算...")
    result = client.calculate(setup)
    result.wait_until_ready()
    print("计算完成！")



    # 4) 提取 GWP100 - 使用新的API方法
    print("\n=== 影响评估结果 ===")

    try:
        # 获取影响类别
        impact_categories = result.get_impact_categories()
        
        # 获取技术流程
        tech_flows = result.get_tech_flows()
        
        if impact_categories and tech_flows:
            # 通常我们关心主要的技术流程（第一个或目标流程）
            main_tech_flow = None
            for tf in tech_flows:
                if hasattr(tf, 'provider') and tf.provider and tf.provider.id == steel.id:
                    main_tech_flow = tf
                    break
            
            if not main_tech_flow and tech_flows:
                main_tech_flow = tech_flows[0]  # 使用第一个技术流程作为备选
            
            if main_tech_flow:
                # 查找气候变化相关的影响类别
                climate_found = False
                for category in impact_categories:
                    if hasattr(category, 'name') and category.name:
                        if any(keyword in category.name.lower() for keyword in 
                            ['climate', 'gwp', 'global warming', '气候']):
                            # 获取该影响类别的总影响值
                            impact_value = result.get_total_impact_of(category, main_tech_flow)
                            
                            # 从 ImpactValue 对象中提取数值
                            value = impact_value.amount
                            unit = getattr(category, 'ref_unit', 'unknown unit')
                            print(f"GWP100: {value:.3f} {unit}")
                            climate_found = True
                
                if not climate_found:
                    print("未找到气候变化相关的影响类别，显示所有影响结果:")
                    # 显示前5个影响类别的结果
                    for i, category in enumerate(impact_categories[:5]):
                        if hasattr(category, 'name') and category.name:
                            try:
                                impact_value = result.get_total_impact_of(category, main_tech_flow)
                                
                                # 从 ImpactValue 对象中提取数值
                                value = impact_value.amount
                                unit = getattr(category, 'ref_unit', 'unknown unit')
                                print(f"{category.name}: {value:.3f} {unit}")
                            except Exception as e:
                                print(f"无法获取 {category.name} 的影响值: {e}")
            else:
                print("未找到技术流程")
        else:
            print("未找到影响类别或技术流程")
            
    except Exception as e:
        print(f"获取影响评估结果时出错: {e}")

    # 清理资源
    if hasattr(result, 'dispose'):
        result.dispose()
    print("\n计算完成，连接已关闭。")

except Exception as e:
    print(f"错误: {e}")
    print("请确保:")
    print("1. openLCA 正在运行")
    print("2. IPC 服务器已启动（端口8080）")
    print("3. 数据库中存在相应的流程和影响评估方法")