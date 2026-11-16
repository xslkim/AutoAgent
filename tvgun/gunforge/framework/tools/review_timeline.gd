extends Control
## Read-only multi-track view. Conditional events get times only after firing.
var owner_tool
var model
var font=ThemeDB.fallback_font
func _gui_input(event):
	if event is InputEventMouseButton and event.pressed and event.button_index==MOUSE_BUTTON_LEFT:
		owner_tool.jump(clampi(int((event.position.x-105)/maxf(1,size.x-115)*owner_tool.session.max_tick),0,owner_tool.session.max_tick))
func _draw():
	if model==null:return
	draw_rect(Rect2(Vector2.ZERO,size),Color("#172033"))
	var labels=["出场 / 运动","任务 / 资源","音效 / 演出","条件（已发生）"]
	for i in range(4):
		draw_string(font,Vector2(5,19+i*25),labels[i],HORIZONTAL_ALIGNMENT_LEFT,-1,12,Color("#cbd5e1"))
		draw_line(Vector2(105,23+i*25),Vector2(size.x-10,23+i*25),Color("#334155"))
	var actual={}
	for entry in model.trace:
		if entry.has("event_id"):actual[entry.event_id]=entry.tick
	for id in model.level.event_order:
		var event=model.level.events[id]
		var at=event.get("at_tick",actual.get(id,-1))
		if at<0:continue
		var lane=3
		if event.has("at_tick"):
			lane=1
			for action in event.actions.values():
				if action.op in ["spawn","remove","set","permission"]:lane=0
				if action.op=="cue":lane=2;break
		var x=105+float(at)/owner_tool.session.max_tick*(size.x-115)
		draw_line(Vector2(x,lane*25+3),Vector2(x,lane*25+22),Color("#59b8aa"),3)
	var cursor=105+float(owner_tool.clock.tick)/owner_tool.session.max_tick*(size.x-115)
	draw_line(Vector2(cursor,0),Vector2(cursor,size.y),Color("#e7b76d"),1)
