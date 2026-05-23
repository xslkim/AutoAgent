#include "AutoAgentProtocolHandler.h"
#include "AutoAgentStableIdResolver.h"
#include "AutoAgentUmgReflector.h"
#include "AutoAgentSlateInputDriver.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "UnrealClient.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "ImageUtils.h"

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
} // namespace

FAutoAgentProtocolHandler::FAutoAgentProtocolHandler()
	: Resolver(MakeShared<FAutoAgentStableIdResolver>()), Reflector(MakeShared<FAutoAgentUmgReflector>(Resolver)), InputDriver(MakeShared<FAutoAgentSlateInputDriver>(Resolver))
{
	Resolver->Load();
}

FAutoAgentProtocolHandler::~FAutoAgentProtocolHandler()
{
	if (ScreenshotViewport.IsValid() && ScreenshotHandle.IsValid())
	{
		ScreenshotViewport->OnScreenshotCaptured().Remove(ScreenshotHandle);
	}
}

void FAutoAgentProtocolHandler::OnScreenshotCaptured(
	int32 Width, int32 Height, const TArray<FColor>& Bitmap)
{
	if (PendingScreenshotPath.IsEmpty() || Bitmap.Num() < Width * Height)
	{
		return;
	}
	const FString Path = PendingScreenshotPath;
	PendingScreenshotPath.Empty();

	// The captured backbuffer alpha is typically 0 — force opaque so the PNG
	// is not saved fully transparent.
	TArray<FColor> Pixels = Bitmap;
	for (FColor& Pixel : Pixels)
	{
		Pixel.A = 255;
	}

	const FImageView Image(Pixels.GetData(), Width, Height, ERawImageFormat::BGRA8);
	if (!FImageUtils::SaveImageByExtension(*Path, Image))
	{
		UE_LOG(LogTemp, Warning, TEXT("[AutoAgent] screenshot save failed: %s"), *Path);
	}
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
		FString TargetId, InputLayer, Button;
		Params->TryGetStringField(TEXT("id"), TargetId);
		Params->TryGetStringField(TEXT("input_layer"), InputLayer);
		Params->TryGetStringField(TEXT("button"), Button);
		if (InputLayer.IsEmpty())
			InputLayer = TEXT("engine");
		if (Button.IsEmpty())
			Button = TEXT("left");
		return InputDriver->Click(TargetId, InputLayer, Button)
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
		FString FromId, ToId, InputLayer;
		Params->TryGetStringField(TEXT("from_id"), FromId);
		Params->TryGetStringField(TEXT("to_id"), ToId);
		Params->TryGetStringField(TEXT("input_layer"), InputLayer);
		if (InputLayer.IsEmpty())
			InputLayer = TEXT("engine");
		return InputDriver->Drag(FromId, ToId, 8, InputLayer)
				   ? BuildResult(Id, MakeShared<FJsonValueNull>())
				   : BuildError(Id, -32001, TEXT("source or destination widget not found"));
	}

	if (Method == TEXT("key_press"))
	{
		FString TargetId, Key, InputLayer;
		Params->TryGetStringField(TEXT("id"), TargetId);
		Params->TryGetStringField(TEXT("key"), Key);
		Params->TryGetStringField(TEXT("input_layer"), InputLayer);
		if (InputLayer.IsEmpty())
			InputLayer = TEXT("engine");
		if (Key.IsEmpty())
			return BuildError(Id, -32602, TEXT("missing param: key"));
		return InputDriver->KeyPress(TargetId, Key, InputLayer)
				   ? BuildResult(Id, MakeShared<FJsonValueNull>())
				   : BuildError(Id, -32001, FString::Printf(TEXT("key press failed: %s"), *TargetId));
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

	if (Method == TEXT("take_screenshot"))
	{
		FString Path;
		Params->TryGetStringField(TEXT("path"), Path);
		if (Path.IsEmpty())
		{
			return BuildError(Id, -32602, TEXT("missing param: path"));
		}

		UGameViewportClient* GameViewport = GEngine ? GEngine->GameViewport : nullptr;
		if (!GameViewport)
		{
			return BuildError(Id, -32603, TEXT("no active game viewport"));
		}

		// Capture via the game viewport's OnScreenshotCaptured delegate: it
		// delivers the scoped game-viewport pixels at the correct post-frame
		// time. We write the file ourselves; fire-and-forget reply.
		PendingScreenshotPath = Path;
		if (ScreenshotViewport.Get() != GameViewport)
		{
			if (ScreenshotViewport.IsValid() && ScreenshotHandle.IsValid())
			{
				ScreenshotViewport->OnScreenshotCaptured().Remove(ScreenshotHandle);
			}
			ScreenshotHandle = GameViewport->OnScreenshotCaptured().AddRaw(
				this, &FAutoAgentProtocolHandler::OnScreenshotCaptured);
			ScreenshotViewport = GameViewport;
		}
		FScreenshotRequest::RequestScreenshot(/*bShowUI=*/true);

		TSharedRef<FJsonObject> ResultObj = MakeShared<FJsonObject>();
		ResultObj->SetStringField(TEXT("path"), Path);
		return BuildResult(Id, MakeShared<FJsonValueObject>(ResultObj));
	}

	if (Method == TEXT("compare_screenshot"))
	{
		// Visual regression capture — saves to the standard Automation/Comparisons
		// directory so CI can diff against baselines/unreal/{platform}/{name}.png.
		//
		// Params:
		//   name      (string, required) — screenshot name, used as the filename stem
		//   threshold (number, optional, default 0.95) — SSIM threshold hint for CI
		//
		// The actual pixel comparison is performed server-side by the Python CI
		// script:  scripts/ci/check_visual_baseline.py
		//   --baseline baselines/unreal/windows/{name}.png
		//   --current  {saved_path}
		//
		// The response is fire-and-forget: the file is written asynchronously by
		// OnScreenshotCaptured; CI should wait for the file before running the
		// comparison script.
		FString Name;
		double Threshold = 0.95;
		Params->TryGetStringField(TEXT("name"), Name);
		Params->TryGetNumberField(TEXT("threshold"), Threshold);

		if (Name.IsEmpty())
		{
			return BuildError(Id, -32602, TEXT("missing param: name"));
		}

		UGameViewportClient* GameViewport = GEngine ? GEngine->GameViewport : nullptr;
		if (!GameViewport)
		{
			return BuildError(Id, -32603, TEXT("no active game viewport"));
		}

		// Standard comparison path: {ProjectSaved}/Automation/Comparisons/{name}.png
		// Matches UE Functional Test automation convention; CI maps this to
		// baselines/unreal/{platform}/{name}.png for SSIM comparison.
		const FString SavePath = FPaths::ConvertRelativePathToFull(
			FPaths::Combine(FPaths::ProjectSavedDir(),
							TEXT("Automation"),
							TEXT("Comparisons"),
							Name + TEXT(".png")));

		PendingScreenshotPath = SavePath;
		if (ScreenshotViewport.Get() != GameViewport)
		{
			if (ScreenshotViewport.IsValid() && ScreenshotHandle.IsValid())
			{
				ScreenshotViewport->OnScreenshotCaptured().Remove(ScreenshotHandle);
			}
			ScreenshotHandle = GameViewport->OnScreenshotCaptured().AddRaw(
				this, &FAutoAgentProtocolHandler::OnScreenshotCaptured);
			ScreenshotViewport = GameViewport;
		}
		FScreenshotRequest::RequestScreenshot(/*bShowUI=*/true);

		TSharedRef<FJsonObject> ResultObj = MakeShared<FJsonObject>();
		ResultObj->SetStringField(TEXT("name"), Name);
		ResultObj->SetStringField(TEXT("saved_path"), SavePath);
		ResultObj->SetNumberField(TEXT("threshold"), Threshold);
		ResultObj->SetStringField(TEXT("status"), TEXT("captured"));
		return BuildResult(Id, MakeShared<FJsonValueObject>(ResultObj));
	}

	return BuildError(Id, -32601, FString::Printf(TEXT("method not found: %s"), *Method));
}
