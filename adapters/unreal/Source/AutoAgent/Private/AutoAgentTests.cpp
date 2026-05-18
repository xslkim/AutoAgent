#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "AutoAgentStableIdResolver.h"
#include "AutoAgentSlateInputDriver.h"
#include "Components/CanvasPanel.h"
#include "Components/Button.h"
#include "Components/EditableTextBox.h"
#include "Components/ScrollBox.h"
#include "UObject/Package.h"

// ---------------------------------------------------------------------------
// StableIdResolver — parses Config/AutoAgentIds.ini.
// ---------------------------------------------------------------------------
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAutoAgentResolverTest,
	"AutoAgent.StableIdResolver",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FAutoAgentResolverTest::RunTest(const FString& /*Parameters*/)
{
	FAutoAgentStableIdResolver Resolver;
	Resolver.Load();

	const FAutoAgentResolvedId Button = Resolver.Resolve(TEXT("LoginButtonBg"));
	TestEqual(TEXT("LoginButtonBg -> pinned id"), Button.PinnedId, FString(TEXT("login_button_bg")));
	TestEqual(TEXT("LoginButtonBg -> logical role"), Button.LogicalRole, FString(TEXT("button")));
	TestTrue(TEXT("LoginButtonBg is pinned"), Button.bPinned);

	const TMap<FString, FString> Sprites = Resolver.GetStateSprites(TEXT("LoginButtonBg"));
	TestEqual(TEXT("button has 4 state sprites"), Sprites.Num(), 4);
	TestTrue(TEXT("state sprites contain normal"), Sprites.Contains(TEXT("normal")));
	TestTrue(TEXT("state sprites contain hover"), Sprites.Contains(TEXT("hover")));
	TestTrue(TEXT("state sprites contain pressed"), Sprites.Contains(TEXT("pressed")));
	TestTrue(TEXT("state sprites contain disabled"), Sprites.Contains(TEXT("disabled")));

	const FAutoAgentResolvedId Unknown = Resolver.Resolve(TEXT("NotARegisteredWidget"));
	TestFalse(TEXT("unregistered widget is not pinned"), Unknown.bPinned);

	return true;
}

// ---------------------------------------------------------------------------
// SlateInputDriver — the four wire-protocol actions against real widgets.
// ---------------------------------------------------------------------------
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAutoAgentInputDriverTest,
	"AutoAgent.InputDriver",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FAutoAgentInputDriverTest::RunTest(const FString& /*Parameters*/)
{
	UCanvasPanel* Root = NewObject<UCanvasPanel>(GetTransientPackage(), TEXT("test_root"));
	UButton* Button = NewObject<UButton>(GetTransientPackage(), TEXT("test_button"));
	UEditableTextBox* TextBox = NewObject<UEditableTextBox>(GetTransientPackage(), TEXT("test_input"));
	UScrollBox* ScrollBox = NewObject<UScrollBox>(GetTransientPackage(), TEXT("test_scroller"));
	Root->AddChild(Button);
	Root->AddChild(TextBox);
	Root->AddChild(ScrollBox);
	Root->AddToRoot();

	TSharedRef<FAutoAgentStableIdResolver> Resolver = MakeShared<FAutoAgentStableIdResolver>();
	Resolver->Load();
	FAutoAgentSlateInputDriver Driver(Resolver);
	Driver.SetSearchRootOverride(Root);

	TestTrue(TEXT("click locates the button"), Driver.Click(TEXT("test_button")));
	TestFalse(TEXT("click on missing node returns false"), Driver.Click(TEXT("no_such_node")));

	TestTrue(TEXT("send_text succeeds"),
		Driver.SendText(TEXT("test_input"), TEXT("hello@test.com")));
	TestEqual(TEXT("send_text sets the text box content"),
		TextBox->GetText().ToString(), FString(TEXT("hello@test.com")));

	TestTrue(TEXT("scroll succeeds"), Driver.Scroll(TEXT("test_scroller"), 0.0f, 50.0f));

	TestTrue(TEXT("drag between two widgets succeeds"),
		Driver.Drag(TEXT("test_button"), TEXT("test_input")));
	TestFalse(TEXT("drag with a missing target returns false"),
		Driver.Drag(TEXT("test_button"), TEXT("no_such_node")));

	Root->RemoveFromRoot();
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
