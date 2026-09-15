package typecases

fun observations(): List<String> {
    val value: Any? = RankedCard("card")
    val holder = Holder(card(value))
    calls = 0
    val named = provide(value) as? Named
    return listOf(
        "${value is Named}:${value is Ranked}:${value is Card}:${value !is Other}",
        "${Other() is Any}:${title(Other())}:${title(null)}",
        "${named?.count() ?: -1}:$calls:${title(value)}",
        "${holder.card?.title ?: "none"}:${Holder(null).card?.count() ?: 0}",
        "${force(Card("yes")).title}:${(value as Card).title}:${card(null) == null}",
        "${scalar("hello")}:${scalar(true)}:${scalar(null)}",
        "${null is Named?}:${value is Named?}:${Other() !is Named}"
    )
}
fun nullFailure(): Card = force(null)
fun castFailure(): Card = provide(Other()) as Card
fun nullCastFailure(): Card = provide(null) as Card
