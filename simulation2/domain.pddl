(define (domain simulation)
	(:requirements :typing :negative-preconditions)
	(:types
		person
		orange
		apple
		knife
		sink
		spoon
		light
		fork
		pen
		fridge
		bowl
		book
		table
		plate
		window
		tv
		channel
		shelf
		level
		bedroom
		kitchen
		livingroom
	)
	(:predicates
		(in-hand ?a - person ?b - (either orange apple knife spoon fork pen bowl book plate))
		(hand-empty ?a - person)
		(sink-contains ?a - sink ?b - (either knife spoon fork bowl plate))
		(faucet-on ?a - sink)
		(light-on ?a - light)
		(fridge-contains ?a - fridge ?b - (either orange apple))
		(table-contains ?a - table ?b - (either orange apple knife spoon fork pen bowl book plate))
		(window-open ?a - window)
		(tv-on ?a - tv)
		(tv-playing-channel ?a - tv ?b - channel)
		(shelf-contains ?a - shelf ?b - (either orange apple knife spoon fork pen bowl book plate) ?c - level)
		(shelf-has-level ?a - shelf ?b - level)
		(in-bedroom ?a - bedroom ?b - (either light table window tv shelf))
		(in-kitchen ?a - kitchen ?b - (either light fridge sink))
		(in-livingroom ?a - livingroom ?b - (either light table window tv shelf))
	)

	(:action place-among-sink
		:parameters (?a - sink ?b - (either knife spoon fork bowl plate) ?c - person)
		:precondition (and
			(in-hand ?c ?b)
		)
		:effect (and
			(not (in-hand ?c ?b))
			(hand-empty ?c)
			(sink-contains ?a ?b)
		)
	)

	(:action remove-from-sink
		:parameters (?a - sink ?b - (either knife spoon fork bowl plate) ?c - person)
		:precondition (and
			(sink-contains ?a ?b)
			(hand-empty ?c)
		)
		:effect (and
			(not (sink-contains ?a ?b))
			(not (hand-empty ?c))
			(in-hand ?c ?b)
		)
	)

	(:action turn-on-faucet
		:parameters (?a - sink)
		:precondition (and
			(not (faucet-on ?a))
		)
		:effect (and
			(faucet-on ?a)
		)
	)

	(:action turn-off-faucet
		:parameters (?a - sink)
		:precondition (and
			(faucet-on ?a)
		)
		:effect (and
			(not (faucet-on ?a))
		)
	)

	(:action turn-on-light
		:parameters (?a - light)
		:precondition (and
			(not (light-on ?a))
		)
		:effect (and
			(light-on ?a)
		)
	)

	(:action turn-off-light
		:parameters (?a - light)
		:precondition (and
			(light-on ?a)
		)
		:effect (and
			(not (light-on ?a))
		)
	)

	(:action place-among-fridge
		:parameters (?a - fridge ?b - (either orange apple) ?c - person)
		:precondition (and
			(in-hand ?c ?b)
		)
		:effect (and
			(not (in-hand ?c ?b))
			(hand-empty ?c)
			(fridge-contains ?a ?b)
		)
	)

	(:action remove-from-fridge
		:parameters (?a - fridge ?b - (either orange apple) ?c - person)
		:precondition (and
			(fridge-contains ?a ?b)
			(hand-empty ?c)
		)
		:effect (and
			(not (fridge-contains ?a ?b))
			(not (hand-empty ?c))
			(in-hand ?c ?b)
		)
	)

	(:action place-among-table
		:parameters (?a - table ?b - (either orange apple knife spoon fork pen bowl book plate) ?c - person)
		:precondition (and
			(in-hand ?c ?b)
		)
		:effect (and
			(not (in-hand ?c ?b))
			(hand-empty ?c)
			(table-contains ?a ?b)
		)
	)

	(:action remove-from-table
		:parameters (?a - table ?b - (either orange apple knife spoon fork pen bowl book plate) ?c - person)
		:precondition (and
			(table-contains ?a ?b)
			(hand-empty ?c)
		)
		:effect (and
			(not (table-contains ?a ?b))
			(not (hand-empty ?c))
			(in-hand ?c ?b)
		)
	)

	(:action open-window
		:parameters (?a - window)
		:precondition (and
			(not (window-open ?a))
		)
		:effect (and
			(window-open ?a)
		)
	)

	(:action close-window
		:parameters (?a - window)
		:precondition (and
			(window-open ?a)
		)
		:effect (and
			(not (window-open ?a))
		)
	)

	(:action turn-tv-on
		:parameters (?a - tv ?b - channel)
		:precondition (and
			(not (tv-on ?a))
		)
		:effect (and
			(tv-on ?a)
			(tv-playing-channel ?a ?b)
		)
	)

	(:action turn-tv-off
		:parameters (?a - tv ?b - channel)
		:precondition (and
			(tv-on ?a)
			(tv-playing-channel ?a ?b)
		)
		:effect (and
			(not (tv-on ?a))
			(not (tv-playing-channel ?a ?b))
		)
	)

	(:action switch-tv-channel
		:parameters (?a - tv ?b - channel ?c - channel)
		:precondition (and
			(tv-playing-channel ?a ?b)
		)
		:effect (and
			(tv-playing-channel ?a ?c)
			(not (tv-playing-channel ?a ?b))
		)
	)

	(:action place-among-shelf
		:parameters (?a - shelf ?b - (either orange apple knife spoon fork pen bowl book plate) ?c - level ?d - person)
		:precondition (and
			(in-hand ?d ?b)
			(shelf-has-level ?a ?c)
		)
		:effect (and
			(not (in-hand ?d ?b))
			(hand-empty ?d)
			(shelf-contains ?a ?b ?c)
		)
	)

	(:action remove-from-shelf
		:parameters (?a - shelf ?b - (either orange apple knife spoon fork pen bowl book plate) ?c - level ?d - person)
		:precondition (and
			(shelf-contains ?a ?b ?c)
			(hand-empty ?d)
		)
		:effect (and
			(not (shelf-contains ?a ?b ?c))
			(not (hand-empty ?d))
			(in-hand ?d ?b)
		)
	)
)
