from .flow_row import FlowRow


class ContextualFlowRow(FlowRow):
    name = 'ContextualFlowRow'
    arguments = FlowRow.arguments | {'itemCount'}

    def project(self, context):
        facts = super().project(context)
        count = context.value('itemCount')
        if type(count) is not int or not 0 <= count <= 200:
            context.issue('itemCount', 'contextual flow requires a resolved finite item count (0..200)')
            count = None
        facts['item_count'] = count
        return facts
