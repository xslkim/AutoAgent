#include "AutoAgentProtocolHandler.h"
#include "AutoAgentStableIdResolver.h"
#include "AutoAgentUmgReflector.h"
#include "AutoAgentSlateInputDriver.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace
{
	FString SerializeObject(const TSharedRef<FJsonObject>& Obj)
	{
		FString Out;
		TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Writer =
			TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Out);
		FJsonSerializer::Serialize(Obj, Writer);
		return Out;
	}

	FString BuildResult(const TSharedPtr<FJsonValue>& Id, const TSharedPtr<FJsonValue>& Result)
	{
		TSharedRef<FJsonObject> Resp = MakeShared<FJsonObject>();
		Resp->SetStringField(TEXT("jsonrpc"), TEXT("2.0"));
		Resp->SetField(TEXT("id"), Id.IsValid() ? Id : MakeShared<FJsonValueNull>());
		Resp->SetField(TEXT("result"), Result.IsValid() ? Result : MakeShared<FJsonValueNull>());
		return SerializeObject(Resp);
	}

	FString BuildError(const TSharedPtr<FJsonValue>& Id, int32 Code, const FString& Message)
	{
		TSharedRef<FJsonObject> ErrObj = MakeShared<FJsonObject>();
		ErrObj->SetNumberField(TEXT("code"), Code);
		ErrObj->SetStringField(TEXT("message"), Message);

		TSharedRef<FJsonObject> Resp = MakeShared<FJsonObject>();
		Resp->SetStringField(TEXT("jsonrpc"), TEXT("2.0"));
		Resp->SetField(TEXT("id"), Id.IsValid() ? Id : MakeShared<FJsonValueNull>());
		Resp->SetObjectField(TEXT("error"), ErrObj);
		return SerializeObject(Resp);
	}
}

FAutoAgentProtocolHandler::FAutoAgentProtocolHandler()
	: Resolver(MakeShared<FAutoAgentStableIdResolver>())
	, Reflector(MakeShared<FAutoAgentUmgReflector>(Resolver))
	, InputDriver(MakeShared<FAutoAgentSlateInputDriver>(Resolver))
{
	Resolver->Load();
}

FString FAutoAgentProtocolHandler::Dispatch(const FString& RequestJson)
{
	TSharedPtr<FJsonObject> Root;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(RequestJson);
	if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
	{
		return BuildError(nullptr, -32700, TEXT("parse error"));
	}

	FString Method;
	Root->TryGetStringField(TEXT("method"), Method);

	TSharedPtr<FJsonValue> Id;
	if (const TSharedPtr<FJsonValue>* IdPtr = Root->Values.Find(TEXT("id")))
	{
		Id = *IdPtr;
	}

	TSharedPtr<FJsonObject> Params = MakeShared<FJsonObject>();
	const TSharedPtr<FJsonObject>* ParamsPtr = nullptr;
	if (Root->TryGetObjectField(TEXT("params"), ParamsPtr) && ParamsPtr)
	{
		Params = *ParamsPtr;
	}

	if (Method == TEXT("negotiate_version"))
	{
		TSharedRef<FJsonObject> ResultObj = MakeShared<FJsonObject>();
		ResultObj->SetStringField(TEXT("server_version"), TEXT("0.1"));
		ResultObj->SetBoolField(TEXT("accepted"), true);
		return BuildResult(Id, MakeShared<FJsonValueObject>(ResultObj));
	}

	if (Method == TEXT("dump_tree"))
	{
		return BuildResult(Id, MakeShared<FJsonValueArray>(Reflector->DumpTree()));
	}

	if (Method == TEXT("find_widget"))
	{
		FString Role;
		Params->TryGetStringField(TEXT("logical_role"), Role);

		TArray<TSharedPtr<FJsonValue>> Matches;
		for (const TSharedPtr<FJsonValue>& NodeVal : Reflector->DumpTree())
		{
			const TSharedPtr<FJsonObject>& Node = NodeVal->AsObject();
			if (!Node.IsValid())
			{
				continue;
			}
			if (!Role.IsEmpty())
			{
				const TSharedPtr<FJsonObject>* MetaPtr = nullptr;
				FString NodeRole;
				if (Node->TryGetObjectField(TEXT("meta"), MetaPtr) && MetaPtr)
				{
					(*MetaPtr)->TryGetStringField(TEXT("logical_role"), NodeRole);
				}
				if (NodeRole != Role)
				{
					continue;
				}
			}
			FString NodeId;
			Node->TryGetStringField(TEXT("id"), NodeId);
			Matches.Add(MakeShared<FJsonValueString>(NodeId));
		}
		return BuildResult(Id, MakeShared<FJsonValueArray>(Matches));
	}

	if (Method == TEXT("get_widget"))
	{
		FString TargetId;
		Params->TryGetStringField(TEXT("id"), TargetId);
		for (const TSharedPtr<FJsonValue>& NodeVal : Reflector->DumpTree())
		{
			const TSharedPtr<FJsonObject>& Node = NodeVal->AsObject();
			FString NodeId;
			if (Node.IsValid() && Node->TryGetStringField(TEXT("id"), NodeId) && NodeId == TargetId)
			{
				return BuildResult(Id, NodeVal);
			}
		}
		return BuildError(Id, -32001, FString::Printf(TEXT("widget not found: %s"), *TargetId));
	}

	if (Method == TEXT("click"))
	{
		FString TargetId;
		Params->TryGetStringField(TEXT("id"), TargetId);
		return InputDriver->Click(TargetId)
			? BuildResult(Id, MakeShared<FJsonValueNull>())
			: BuildError(Id, -32001, FString::Printf(TEXT("widget not found: %s"), *TargetId));
	}

	if (Method == TEXT("send_text"))
	{
		FString TargetId, Text;
		Params->TryGetStringField(TEXT("id"), TargetId);
		Params->TryGetStringField(TEXT("text"), Text);
		return InputDriver->SendText(TargetId, Text)
			? BuildResult(Id, MakeShared<FJsonValueNull>())
			: BuildError(Id, -32001, FString::Printf(TEXT("widget not found or not editable: %s"), *TargetId));
	}

	if (Method == TEXT("drag"))
	{
		FString FromId, ToId;
		Params->TryGetStringField(TEXT("from_id"), FromId);
		Params->TryGetStringField(TEXT("to_id"), ToId);
		return InputDriver->Drag(FromId, ToId)
			? BuildResult(Id, MakeShared<FJsonValueNull>())
			: BuildError(Id, -32001, TEXT("source or destination widget not found"));
	}

	if (Method == TEXT("scroll"))
	{
		FString TargetId;
		double DeltaX = 0.0, DeltaY = 0.0;
		Params->TryGetStringField(TEXT("id"), TargetId);
		Params->TryGetNumberField(TEXT("delta_x"), DeltaX);
		Params->TryGetNumberField(TEXT("delta_y"), DeltaY);
		return InputDriver->Scroll(TargetId, static_cast<float>(DeltaX), static_cast<float>(DeltaY))
			? BuildResult(Id, MakeShared<FJsonValueNull>())
			: BuildError(Id, -32001, FString::Printf(TEXT("widget not found: %s"), *TargetId));
	}

	return BuildError(Id, -32601, FString::Printf(TEXT("method not found: %s"), *Method));
}
