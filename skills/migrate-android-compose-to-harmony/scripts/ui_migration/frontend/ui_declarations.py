"""Named native content slots; source declarations live in SourceSymbolIndex."""
NATIVE_SLOTS = {
    'ListItem': {'headlineContent', 'supportingContent', 'overlineContent', 'leadingContent', 'trailingContent'},
    'FilterChip': {'label', 'leadingIcon', 'trailingIcon'},
    'ExtendedFloatingActionButton': {'icon', 'text', 'content'},
    'Layout': {'content'},
    'Scaffold': {'topBar', 'bottomBar', 'content', 'snackbarHost', 'floatingActionButton'},
    'TopAppBar': {'title', 'navigationIcon', 'actions'},
    'LargeFlexibleTopAppBar': {'title', 'subtitle', 'navigationIcon', 'actions'},
    'CenterAlignedTopAppBar': {'title', 'navigationIcon', 'actions'},
    'BottomAppBar': {'actions', 'floatingActionButton', 'content'},
    'DecorationBox': {'leadingIcon', 'trailingIcon', 'placeholder', 'label', 'supportingText', 'container', 'innerTextField'},
}
