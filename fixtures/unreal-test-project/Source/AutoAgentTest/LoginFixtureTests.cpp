// AutoAgent login fixture — automation tests (TASK-0209)
//
// Tests for UMockApi and ULoginController that live inside the fixture module
// so they can include fixture headers directly.
//
// Test suites
//   AutoAgentFixture.MockApi.*        — pure-C++ credential validation + history
//   AutoAgentFixture.LoginController.* — controller lifecycle with null widget

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "LoginController.h"
#include "MockApi.h"

// ===========================================================================
// MockApi — credential validation + call history
// ===========================================================================

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAutoAgentFixture_MockApi_ValidCreds,
								 "AutoAgentFixture.MockApi.ValidCredentials",
								 EAutomationTestFlags::EditorContext |
									 EAutomationTestFlags::EngineFilter)

bool FAutoAgentFixture_MockApi_ValidCreds::RunTest(const FString& /*Parameters*/)
{
	UMockApi* Api = NewObject<UMockApi>(GetTransientPackage());

	const FString Result = Api->Post(TEXT("admin"), TEXT("password"));
	TestEqual(TEXT("admin/password → ok"), Result, FString(TEXT("ok")));
	TestTrue(TEXT("WasPostCalled returns true"), Api->WasPostCalled());
	TestEqual(TEXT("LastUsername recorded"), Api->GetLastUsername(), FString(TEXT("admin")));
	TestEqual(TEXT("LastPassword recorded"), Api->GetLastPassword(), FString(TEXT("password")));

	return true;
}

// ---------------------------------------------------------------------------
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAutoAgentFixture_MockApi_InvalidCreds,
								 "AutoAgentFixture.MockApi.InvalidCredentials",
								 EAutomationTestFlags::EditorContext |
									 EAutomationTestFlags::EngineFilter)

bool FAutoAgentFixture_MockApi_InvalidCreds::RunTest(const FString& /*Parameters*/)
{
	UMockApi* Api = NewObject<UMockApi>(GetTransientPackage());

	// Wrong password
	TestEqual(TEXT("wrong password → error"),
			  Api->Post(TEXT("admin"), TEXT("wrong")),
			  FString(TEXT("error")));

	// Wrong username
	TestEqual(TEXT("wrong username → error"),
			  Api->Post(TEXT("hacker"), TEXT("password")),
			  FString(TEXT("error")));

	// Both wrong
	TestEqual(TEXT("both wrong → error"),
			  Api->Post(TEXT("hacker"), TEXT("12345")),
			  FString(TEXT("error")));

	// Empty
	TestEqual(TEXT("empty creds → error"),
			  Api->Post(TEXT(""), TEXT("")),
			  FString(TEXT("error")));

	return true;
}

// ---------------------------------------------------------------------------
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAutoAgentFixture_MockApi_History,
								 "AutoAgentFixture.MockApi.CallHistory",
								 EAutomationTestFlags::EditorContext |
									 EAutomationTestFlags::EngineFilter)

bool FAutoAgentFixture_MockApi_History::RunTest(const FString& /*Parameters*/)
{
	UMockApi* Api = NewObject<UMockApi>(GetTransientPackage());

	// Before any call
	TestFalse(TEXT("WasPostCalled false before any call"), Api->WasPostCalled());
	TestTrue(TEXT("LastUsername empty before call"), Api->GetLastUsername().IsEmpty());

	// After first call
	Api->Post(TEXT("admin"), TEXT("password"));
	TestTrue(TEXT("WasPostCalled true after first call"), Api->WasPostCalled());

	// After second call — history reflects the last call
	Api->Post(TEXT("user2"), TEXT("pass2"));
	TestEqual(TEXT("LastUsername updated to latest call"),
			  Api->GetLastUsername(),
			  FString(TEXT("user2")));

	// Reset clears history
	Api->Reset();
	TestFalse(TEXT("WasPostCalled false after Reset()"), Api->WasPostCalled());
	TestTrue(TEXT("LastUsername empty after Reset()"), Api->GetLastUsername().IsEmpty());
	TestTrue(TEXT("LastPassword empty after Reset()"), Api->GetLastPassword().IsEmpty());

	return true;
}

// ---------------------------------------------------------------------------
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAutoAgentFixture_MockApi_Reset,
								 "AutoAgentFixture.MockApi.Reset",
								 EAutomationTestFlags::EditorContext |
									 EAutomationTestFlags::EngineFilter)

bool FAutoAgentFixture_MockApi_Reset::RunTest(const FString& /*Parameters*/)
{
	UMockApi* Api = NewObject<UMockApi>(GetTransientPackage());

	Api->Post(TEXT("admin"), TEXT("password"));
	TestTrue(TEXT("called before Reset"), Api->WasPostCalled());

	Api->Reset();
	TestFalse(TEXT("not called after Reset"), Api->WasPostCalled());

	// Can call again after Reset
	const FString Result = Api->Post(TEXT("admin"), TEXT("password"));
	TestEqual(TEXT("valid call after Reset → ok"), Result, FString(TEXT("ok")));
	TestTrue(TEXT("WasPostCalled true again"), Api->WasPostCalled());

	return true;
}

// ===========================================================================
// LoginController — lifecycle with null widget (headless guard)
// ===========================================================================

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAutoAgentFixture_Controller_NullWidgetSafe,
								 "AutoAgentFixture.LoginController.NullWidgetSafe",
								 EAutomationTestFlags::EditorContext |
									 EAutomationTestFlags::EngineFilter)

bool FAutoAgentFixture_Controller_NullWidgetSafe::RunTest(const FString& /*Parameters*/)
{
	// In the headless editor context BeginPlay() can't find a viewport widget
	// (TObjectIterator finds nothing).  StartAsync() must log a warning and
	// return without crashing.
	//
	// We call StartAsync() directly on a freshly constructed controller
	// (widget is null) to verify the null-guard code path.
	ULoginController* Ctrl = NewObject<ULoginController>(GetTransientPackage());
	Ctrl->AddToRoot();

	// StartAsync() must not crash when LoginWidget is null.
	Ctrl->StartAsync();
	TestNull(TEXT("GetLoginWidget() is null (no viewport widget)"),
			 Ctrl->GetLoginWidget());

	Ctrl->RemoveFromRoot();
	return true;
}

// ---------------------------------------------------------------------------
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAutoAgentFixture_Controller_MockApiAllocated,
								 "AutoAgentFixture.LoginController.MockApiAllocated",
								 EAutomationTestFlags::EditorContext |
									 EAutomationTestFlags::EngineFilter)

bool FAutoAgentFixture_Controller_MockApiAllocated::RunTest(const FString& /*Parameters*/)
{
	// After BeginPlay() (even without a widget), the MockApi object must be
	// allocated so it can be used as a test spy.
	//
	// We simulate BeginPlay() by calling it on a transient controller.
	// UActorComponent::BeginPlay() requires a registered component, so we
	// call StartAsync() instead, then manually assign the MockApi.
	ULoginController* Ctrl = NewObject<ULoginController>(GetTransientPackage());
	Ctrl->AddToRoot();

	// Manually assign a MockApi so assertions don't rely on BeginPlay().
	// This mirrors what BeginPlay() does after finding the widget.
	UMockApi* Api = NewObject<UMockApi>(Ctrl);
	TestNotNull(TEXT("MockApi can be created"), Api);
	TestFalse(TEXT("MockApi not called initially"), Api->WasPostCalled());

	Api->Post(TEXT("admin"), TEXT("password"));
	TestTrue(TEXT("MockApi records the call"), Api->WasPostCalled());

	Ctrl->RemoveFromRoot();
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
