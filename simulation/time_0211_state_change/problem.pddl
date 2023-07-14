(define (problem simulation-a)
	(:domain simulation)
	(:objects
		me - person
		jane-bedroom - bedroom
		jane-bedroom-shelf - shelf
		jane-bedroom-table - table
		jane-bedroom-tv - tv
		jane-bedroom-overhead-light - light
		jane-bedroom-window - window
		living-room - livingroom
		living-room-overhead-light - light
		living-room-tv - tv
		living-room-shelf - shelf
		living-room-window - window
		living-room-table - table
		john-bedroom - bedroom
		john-bedroom-overhead-light - light
		john-bedroom-window - window
		john-bedroom-tv - tv
		john-bedroom-shelf - shelf
		john-bedroom-table - table
		kitchen - kitchen
		kitchen-overhead-light - light
		kitchen-fridge - fridge
		kitchen-sink - sink
		red-pen - pen
		spoon - spoon
		white-pen - pen
		orange - orange
		fahrenheit-451-book - book
		apple - apple
		purple-pen - pen
		alchemist-book - book
		bowl - bowl
		of-mice-and-men-book - book
		knife - knife
		plate - plate
		fork - fork
		the-discovery-channel - channel
		cartoon-network - channel
		nbc - channel
		cnn - channel
		fox-news - channel
		espn - channel
		level-1 - level
		level-2 - level
		level-3 - level
		level-4 - level
		level-5 - level
		level-6 - level
		level-7 - level
		level-8 - level
		level-9 - level
		level-10 - level
	)
	(:init
		(in-bedroom jane-bedroom jane-bedroom-shelf)
		(shelf-has-level jane-bedroom-shelf level-1)
		(shelf-has-level jane-bedroom-shelf level-2)
		(shelf-has-level jane-bedroom-shelf level-3)
		(shelf-has-level jane-bedroom-shelf level-4)
		(shelf-has-level jane-bedroom-shelf level-5)
		(shelf-has-level jane-bedroom-shelf level-6)
		(in-bedroom jane-bedroom jane-bedroom-table)
		(in-bedroom jane-bedroom jane-bedroom-tv)
		(in-bedroom jane-bedroom jane-bedroom-overhead-light)
		(light-on jane-bedroom-overhead-light)
		(in-bedroom jane-bedroom jane-bedroom-window)
		(in-livingroom living-room living-room-overhead-light)
		(in-livingroom living-room living-room-tv)
		(tv-on living-room-tv)
		(tv-playing-channel living-room-tv cartoon-network)
		(in-livingroom living-room living-room-shelf)
		(shelf-has-level living-room-shelf level-1)
		(shelf-has-level living-room-shelf level-2)
		(shelf-has-level living-room-shelf level-3)
		(shelf-has-level living-room-shelf level-4)
		(shelf-has-level living-room-shelf level-5)
		(shelf-has-level living-room-shelf level-6)
		(shelf-has-level living-room-shelf level-7)
		(shelf-has-level living-room-shelf level-8)
		(shelf-has-level living-room-shelf level-9)
		(shelf-has-level living-room-shelf level-10)
		(in-livingroom living-room living-room-window)
		(in-livingroom living-room living-room-table)
		(in-bedroom john-bedroom john-bedroom-overhead-light)
		(in-bedroom john-bedroom john-bedroom-window)
		(in-bedroom john-bedroom john-bedroom-tv)
		(tv-on john-bedroom-tv)
		(tv-playing-channel john-bedroom-tv cartoon-network)
		(in-bedroom john-bedroom john-bedroom-shelf)
		(shelf-has-level john-bedroom-shelf level-1)
		(shelf-has-level john-bedroom-shelf level-2)
		(shelf-has-level john-bedroom-shelf level-3)
		(shelf-has-level john-bedroom-shelf level-4)
		(shelf-has-level john-bedroom-shelf level-5)
		(in-bedroom john-bedroom john-bedroom-table)
		(in-kitchen kitchen kitchen-overhead-light)
		(in-kitchen kitchen kitchen-fridge)
		(in-kitchen kitchen kitchen-sink)
		(shelf-contains john-bedroom-shelf red-pen level-2)
		(shelf-contains living-room-shelf spoon level-9)
		(table-contains john-bedroom-table white-pen)
		(in-hand me orange)
		(table-contains living-room-table fahrenheit-451-book)
		(table-contains jane-bedroom-table apple)
		(table-contains living-room-table purple-pen)
		(table-contains living-room-table alchemist-book)
		(shelf-contains john-bedroom-shelf bowl level-1)
		(table-contains living-room-table of-mice-and-men-book)
		(table-contains john-bedroom-table knife)
		(sink-contains kitchen-sink plate)
		(shelf-contains john-bedroom-shelf fork level-4)
	)
)
