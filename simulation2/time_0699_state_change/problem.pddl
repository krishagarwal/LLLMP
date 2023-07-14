(define (problem simulation-a)
	(:domain simulation)
	(:objects
		me - person
		living-room - livingroom
		living-room-window - window
		living-room-shelf - shelf
		living-room-tv - tv
		living-room-table - table
		living-room-overhead-light - light
		kitchen - kitchen
		kitchen-sink - sink
		kitchen-fridge - fridge
		kitchen-overhead-light - light
		mark-bedroom - bedroom
		mark-bedroom-window - window
		mark-bedroom-shelf - shelf
		mark-bedroom-table - table
		mark-bedroom-tv - tv
		mark-bedroom-overhead-light - light
		linda-bedroom - bedroom
		linda-bedroom-shelf - shelf
		linda-bedroom-tv - tv
		linda-bedroom-table - table
		linda-bedroom-overhead-light - light
		linda-bedroom-window - window
		fork - fork
		bowl - bowl
		of-mice-and-men-book - book
		apple - apple
		orange - orange
		knife - knife
		purple-pen - pen
		black-pen - pen
		tom-sawyer-book - book
		plate - plate
		spoon - spoon
		lord-of-the-rings-book - book
		blue-pen - pen
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
		(in-livingroom living-room living-room-window)
		(in-livingroom living-room living-room-shelf)
		(shelf-has-level living-room-shelf level-1)
		(shelf-has-level living-room-shelf level-2)
		(shelf-has-level living-room-shelf level-3)
		(shelf-has-level living-room-shelf level-4)
		(in-livingroom living-room living-room-tv)
		(in-livingroom living-room living-room-table)
		(in-livingroom living-room living-room-overhead-light)
		(in-kitchen kitchen kitchen-sink)
		(faucet-on kitchen-sink)
		(in-kitchen kitchen kitchen-fridge)
		(in-kitchen kitchen kitchen-overhead-light)
		(light-on kitchen-overhead-light)
		(in-bedroom mark-bedroom mark-bedroom-window)
		(window-open mark-bedroom-window)
		(in-bedroom mark-bedroom mark-bedroom-shelf)
		(shelf-has-level mark-bedroom-shelf level-1)
		(shelf-has-level mark-bedroom-shelf level-2)
		(shelf-has-level mark-bedroom-shelf level-3)
		(shelf-has-level mark-bedroom-shelf level-4)
		(shelf-has-level mark-bedroom-shelf level-5)
		(shelf-has-level mark-bedroom-shelf level-6)
		(shelf-has-level mark-bedroom-shelf level-7)
		(shelf-has-level mark-bedroom-shelf level-8)
		(shelf-has-level mark-bedroom-shelf level-9)
		(shelf-has-level mark-bedroom-shelf level-10)
		(in-bedroom mark-bedroom mark-bedroom-table)
		(in-bedroom mark-bedroom mark-bedroom-tv)
		(in-bedroom mark-bedroom mark-bedroom-overhead-light)
		(light-on mark-bedroom-overhead-light)
		(in-bedroom linda-bedroom linda-bedroom-shelf)
		(shelf-has-level linda-bedroom-shelf level-1)
		(shelf-has-level linda-bedroom-shelf level-2)
		(shelf-has-level linda-bedroom-shelf level-3)
		(shelf-has-level linda-bedroom-shelf level-4)
		(shelf-has-level linda-bedroom-shelf level-5)
		(shelf-has-level linda-bedroom-shelf level-6)
		(shelf-has-level linda-bedroom-shelf level-7)
		(shelf-has-level linda-bedroom-shelf level-8)
		(shelf-has-level linda-bedroom-shelf level-9)
		(shelf-has-level linda-bedroom-shelf level-10)
		(in-bedroom linda-bedroom linda-bedroom-tv)
		(tv-on linda-bedroom-tv)
		(tv-playing-channel linda-bedroom-tv fox-news)
		(in-bedroom linda-bedroom linda-bedroom-table)
		(in-bedroom linda-bedroom linda-bedroom-overhead-light)
		(light-on linda-bedroom-overhead-light)
		(in-bedroom linda-bedroom linda-bedroom-window)
		(table-contains linda-bedroom-table fork)
		(in-hand me bowl)
		(shelf-contains living-room-shelf of-mice-and-men-book level-2)
		(shelf-contains mark-bedroom-shelf apple level-1)
		(shelf-contains mark-bedroom-shelf orange level-5)
		(shelf-contains mark-bedroom-shelf knife level-4)
		(shelf-contains linda-bedroom-shelf purple-pen level-2)
		(table-contains mark-bedroom-table black-pen)
		(table-contains linda-bedroom-table tom-sawyer-book)
		(shelf-contains mark-bedroom-shelf plate level-5)
		(table-contains mark-bedroom-table spoon)
		(shelf-contains living-room-shelf lord-of-the-rings-book level-2)
		(shelf-contains mark-bedroom-shelf blue-pen level-6)
	)
)
