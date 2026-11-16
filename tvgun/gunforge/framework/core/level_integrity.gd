extends RefCounted
## Cross-language JSON digest: numeric values normalize to IEEE754 f64 LE bytes.
static func normalize(value):
	match typeof(value):
		TYPE_INT,TYPE_FLOAT:
			var bytes=PackedByteArray();bytes.resize(8);bytes.encode_double(0,float(value))
			return {"@number":bytes.hex_encode()}
		TYPE_ARRAY:
			var out=[]
			for item in value:out.append(normalize(item))
			return out
		TYPE_DICTIONARY:
			var out={}
			for key in value:out[key]=normalize(value[key])
			return out
	return value
static func digest(value):return JSON.stringify(normalize(value),"",true).sha256_text()
