extends RefCounted

var matrix = [1.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0]

func apply(p: Vector2) -> Vector2:
	var d = matrix[6]*p.x+matrix[7]*p.y+1
	if absf(d)<.00001:
		return Vector2(INF,INF)
	return Vector2((matrix[0]*p.x+matrix[1]*p.y+matrix[2])/d,
					(matrix[3]*p.x+matrix[4]*p.y+matrix[5])/d)

func fit(from: Array, to: Array) -> bool:
	if from.size()<5 or from.size()!=to.size():
		return false
	var rows = []
	var values = []
	for i in range(from.size()):
		var x = from[i].x/1920
		var y = from[i].y/1080
		var u = to[i].x/1920
		var v = to[i].y/1080
		rows.append([x,y,1.0,0.0,0.0,0.0,-u*x,-u*y])
		rows.append([0.0,0.0,0.0,x,y,1.0,-v*x,-v*y])
		values.append(u)
		values.append(v)
	var normal = []
	for i in range(8):
		var row = []
		for j in range(8):
			var value = 0.0
			for r in rows:
				value += r[i]*r[j]
			row.append(value)
		var rhs = 0.0
		for k in range(rows.size()):
			rhs += rows[k][i]*values[k]
		row.append(rhs)
		normal.append(row)
	for col in range(8):
		var pivot = col
		for i in range(col+1,8):
			if absf(normal[i][col])>absf(normal[pivot][col]):
				pivot = i
		if absf(normal[pivot][col])<1e-9:
			return false
		var temp = normal[pivot]
		normal[pivot] = normal[col]
		normal[col] = temp
		var divisor = normal[col][col]
		for j in range(col,9):
			normal[col][j] /= divisor
		for i in range(8):
			if i==col:
				continue
			var factor = normal[i][col]
			for j in range(col,9):
				normal[i][j] -= factor*normal[col][j]
	var a = []
	for i in range(8):
		a.append(normal[i][8])
	matrix = [a[0],a[1]*1920/1080,a[2]*1920,
			  a[3]*1080/1920,a[4],a[5]*1080,a[6]/1920,a[7]/1080]
	return true
