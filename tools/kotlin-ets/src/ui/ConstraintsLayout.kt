package dev.ets

/** Subcompose after receiving real native constraints, without changing @State during measurement. */
internal val constraintsLayoutSupport = """
@Builder
function __etsEmptyConstraints(args: __etsConstraintArgs) {}
class __etsEmptyConstraintData {}

class __etsConstraintFrame extends __etsFrameNode {
  private context: __etsUIContext;
  private subtree: __etsBuilderNode<[__etsConstraintArgs]>;
  private host: EtsComposeBoxWithConstraints;
  private lastKey: string = '';
  private dirty: boolean = true;
  private built: boolean = false;
  private bounds: __etsBoxConstraints = new __etsBoxConstraints(0, 0, 0, 0);

  constructor(context: __etsUIContext, host: EtsComposeBoxWithConstraints) {
    super(context);
    this.context = context;
    this.host = host;
    this.subtree = new __etsBuilderNode<[__etsConstraintArgs]>(context);
  }

  refresh(): void {
    this.dirty = true;
    this.setNeedsLayout();
  }

  onMeasure(incoming: __etsLayoutConstraint): void {
    const constraint: __etsLayoutConstraint = {
      minSize: {
        width: this.host.fixedWidth ? incoming.maxSize.width : incoming.minSize.width,
        height: this.host.fixedHeight ? incoming.maxSize.height : incoming.minSize.height
      },
      maxSize: incoming.maxSize,
      percentReference: incoming.percentReference
    };
    const key = JSON.stringify(constraint);
    if (!this.built || this.dirty || this.lastKey !== key) {
      this.bounds = new __etsBoxConstraints(
        this.context.px2vp(constraint.minSize.width), this.context.px2vp(constraint.minSize.height),
        this.context.px2vp(constraint.maxSize.width), this.context.px2vp(constraint.maxSize.height));
      const args = new __etsConstraintArgs(UIUtils.makeBinding(() => this.bounds), this.host.data, this.host.alignment);
      if (!this.built) {
        this.subtree.build(this.host.content, args, { nestingBuilderSupported: true });
        this.appendChild(this.subtree.getFrameNode()!);
        this.built = true;
      } else {
        this.subtree.update(args);
      }
      this.lastKey = key;
      this.dirty = false;
    }
    const child = this.subtree.getFrameNode()!;
    child.measure(constraint);
    this.setMeasuredSize(child.getMeasuredSize());
  }

  onLayout(position: Position): void {
    this.setLayoutPosition({ x: Number(position.x), y: Number(position.y) });
    this.subtree.getFrameNode()!.layout({ x: 0, y: 0 });
  }

  release(): void {
    this.subtree.dispose();
    this.dispose();
  }
}

class __etsConstraintController extends __etsNodeController {
  private host: EtsComposeBoxWithConstraints;
  private node: __etsConstraintFrame | null = null;
  constructor(host: EtsComposeBoxWithConstraints) {
    super();
    this.host = host;
  }
  makeNode(context: __etsUIContext): __etsFrameNode | null {
    this.node = new __etsConstraintFrame(context, this.host);
    return this.node;
  }
  refresh(): void { this.node?.refresh(); }
  release(): void { this.node?.release(); this.node = null; }
}

@Component
struct EtsComposeBoxWithConstraints {
  @Prop @Watch('refresh') content: WrappedBuilder<[__etsConstraintArgs]> = new WrappedBuilder<[__etsConstraintArgs]>(__etsEmptyConstraints);
  @Prop @Watch('refresh') data: Object = new __etsEmptyConstraintData();
  @Prop @Watch('refresh') alignment: Alignment = Alignment.TopStart;
  @Prop @Watch('refresh') fixedWidth: boolean = false;
  @Prop @Watch('refresh') fixedHeight: boolean = false;
  private controller: __etsConstraintController = new __etsConstraintController(this);
  refresh(): void { this.controller.refresh(); }
  aboutToBeDeleted(): void { this.controller.release(); }
  build() {
    NodeContainer(this.controller)
  }
}
""".trimIndent().lines()
