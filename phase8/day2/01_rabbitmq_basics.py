import os,sys
sys.path.insert(0,os.path.dirname(__file__))

import asyncio
import time
import uuid
from datetime import datetime,timezone
from typing import Optional,Callable
import aio_pika
import json

# ============================================================
# CONNECTION SETTINGS
# ============================================================
RABBITMQ_URL=os.getenv(
    "RABBITMQ_URL",
    "ampq://admin:admin123@localhost:5672"
    # ampq=Advanced Message Queuing Protocol -> RabbitMQ native language
)

# ============================================================
# BASIC PRODUCER — send messages to a queue
# ============================================================
async def basic_producer():
    """
    Simplest possible producer.
    Connects → sends messages → disconnects.
    """
    print("\n=== Basic Producer ===")

    # Connect to RabbitMQ
    # Creates a TCP connection to RabbitMQ on port 5672
    connection=await aio_pika.connect_robust(url=RABBITMQ_URL)

    async with connection:
        # Create a channel (like a session inside a connection)
        # Creates a lightweight "conversation" inside the connection.You could create 100+ channels on 1 connection
        channel=await connection.channel()

        # Declare the queue — creates it if not exists
        # durable=True → queue survives RabbitMQ restart
        # Creates a queue named "documents" (if not exists)
        # durable=True	Queue survives if RabbitMQ restarts (saved to disk)
        queue=await channel.declare_queue(
            name="documents",
            durable=True
        )

        # Send 3 messages
        for i in range(3):
            message_body=json.dumps(
                {
                    "doc_id":f"doc{i}",
                    "filename":f"document_{i}.pdf",
                    "size_mb":round(i*2.5,1),
                    "sent_at":datetime.now(timezone.utc).isoformat(),
                }
            )
            
            # This is using Exchange #1 from your 7 built-in exchanges — the (AMQP default) exchange!
            # Message goes directly to documents queue
            # body => The actual document metadata
            # delivery_mode => PERSISTENT: Save message to disk (survives RabbitMQ restart)
            # message_id => Unique ID for tracking/deduplication
            # content_type => Tells consumer how to parse the body

            await channel.default_exchange.publish(
                message=aio_pika.Message(
                    body=message_body.encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    message_id=str(uuid.uuid4()),
                    content_type="application/json"
                ),
                routing_key=queue.name
            )
            print(f"  → Sent: doc_{i}")
        print(f"  Total messages in queue: {queue.declaration_result.message_count + 3}")


# ============================================================
# BASIC CONSUMER — read messages from a queue
# ============================================================
async def basic_consumer(max_messages:int=3):
    """
    Simplest possible consumer.
    Reads messages and acknowledges them.
    """
    print("\n=== Basic Consumer ===")

    connection=await aio_pika.connect_robust(url=RABBITMQ_URL)
    recieved=0

    async with connection:
        channel=await connection.channel()
        # qos=Quality of service
        # Consumer grabs ONLY 1 message
        await channel.set_qos(prefetch_count=1)

        queue=await channel.declare_queue(name="documents",durable=True)

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                # The magic of message.process()
                # ✅ Success (no exception)	Sends ACK (acknowledgment) — removes message from queue
                # ❌ Exception occurs	Sends NACK (negative acknowledgment) — message returns to queue
                # 💥 Consumer crashes	RabbitMQ redelivers message to another consumer

                async with message.process():
                    body=json.loads(message.body)
                    print(f"  ← Received: {body['doc_id']} ({body['filename']})")
                    print(f"    Processing...")
                    await asyncio.sleep(2.5)    # simulate processing
                    print(f"    ✅ Done — message acknowledged")

                    recieved+=1
                    if recieved>=max_messages:
                        break

async def demo_exchanges():
    """
    Shows the three most useful exchange types.
    """
    print("\n=== Exchange Types ===")

    connection=await aio_pika.connect_robust(url=RABBITMQ_URL)

    async with connection:
        channel=await connection.channel()

        # ---- DIRECT EXCHANGE ----
        # Route by exact routing key
        direct_exchange=await channel.declare_exchange(
            name="it_ops_direct",
            type=aio_pika.ExchangeType.DIRECT,
            durable=True # It tells RabbitMQ: "Save this to disk so it survives a restart"
        )

        # Separate queues per severity
        for severity in ["critical","warning","info"]:
            q=await channel.declare_queue(name=f"alerts_{severity}",durable=True)
            await q.bind(exchange=direct_exchange,routing_key=severity)

        # Send to specific severity queue
        for severity,msg in [
            ("critical","Production DB down"),
            ("warning","High CPU usage"),
            ("info","Deployment complete")
        ]:
            await direct_exchange.publish(
                message=aio_pika.Message(
                    body=json.dumps({"alert":msg,"severity":severity}).encode(), # RMQ reads only in bytes
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                ),
                routing_key=severity
            )
            # Send to specific severity queue

        # ---- TOPIC EXCHANGE ----
        # Route by pattern — like regex but with * and #
        # * = exactly one word
        # # = zero or more words
        topic_exchange=await channel.declare_exchange(
            name="it_ops_topic",
            type=aio_pika.ExchangeType.TOPIC
        )

        # Queue for all LLM events
        llm_q=await channel.declare_queue(name="llm_events",durable=True)
        await llm_q.bind(exchange=topic_exchange,routing_key="llm.*")

        # Queue for all production events
        prod_q=await channel.declare_queue(name="prod_events",durable=True)
        await prod_q.bind(exchange=topic_exchange,routing_key="*.production")

        # Queue for everything
        all_q=await channel.declare_queue(name="all_events",durable=True)
        await all_q.bind(exchange=topic_exchange,routing_key="#")

        # Publish with topic routing keys
        events=[
            ("llm.generation","GTP-4 call completed"),
            ("llm.embeddings","Embeddings generated"),
            ("deploy.production","New version deployed"),
            ("incident.staging","Staging service down")
        ]
        for routing_key,message in events:
            await topic_exchange.publish(
                message=aio_pika.Message(
                    body=json.dumps({"event":message}).encode()
                ),
                routing_key=routing_key
            )
            print(f"  [TOPIC] → {routing_key}: {message}")

        # ---- FANOUT EXCHANGE ----
        # Broadcast to ALL bound queues regardless of routing key
        fanout_exchange=await channel.declare_exchange(
            name="it_ops_broadcast",
            type=aio_pika.ExchangeType.TOPIC,
            durable=True
        )

        # All these queues get the same message
        for service in ["audit_log","notification","monitoring"]:
            q=await channel.declare_queue(name=f"broadcast_{service}",durable=True)
            await q.bind(exchange=fanout_exchange)

        await fanout_exchange.publish(
            message=aio_pika.Message(
                body=json.dumps({"event":"system_shutdown","message":"Maintance window starting"}).encode()
            ),
            routing_key=""
        )
        print("  [FANOUT] → system_shutdown broadcast to all services")


# ============================================================
# DEAD LETTER QUEUE — handle failed messages
# ============================================================
async def demo_ded_letter_queue():
    """
    Dead Letter Queue (DLQ) = where messages go when they fail.

    Without DLQ: failed message → lost forever
    With DLQ:    failed message → DLQ → inspect/replay/alert

    Critical in production — never lose a failed job.
    """
    print("\n=== Dead Letter Queue ===")

    connection=await aio_pika.connect_robust(url=RABBITMQ_URL)

    async with connection:
        channel=await connection.channel()

        # 1. Create the DLQ first
        dlq=await channel.declare_queue(name="documents_failed",durable=True)

        # 2. Create main queue with DLQ configured
        # Messages that fail → automatically sent to documents_failed
        main_q=await channel.declare_queue(
            name="documents_with_dlq",
            durable=True, # ✅ The shelf itself is made of metal
            arguments={
                "x-dead-letter-exchange":"",
                "x-dead-letter-routing-key":"documents_failed",
                "x-message-ttl":60000,
                "x-max-retries":3
            }
        )

        # Send a message that will "fail"
        await channel.default_exchange.publish(
            message=aio_pika.Message(
                body=json.dumps({"doc_id":"bad_doc","will_fail":True}).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT #  ✅ Written in permanent ink
            ),
            routing_key=main_q.name
        )
        print("  Sent message that will fail processing")

        # Consumer that rejects bad messages
        async def process_with_failures(message:aio_pika.IncomingMessage):
            body=json.loads(message.body)
            if body.get("will_fail"):
                print(f"  ❌ Processing failed for {body['doc_id']} → sent to DLQ")
                await message.reject(requeue=False) # Chef just says: "I can't make this order, and don't put it back on my shelf."
                #The manager sees:
                # Chef rejected order from documents_with_dlq shelf
                # requeue=False (don't put back on same shelf)
                # Manager checks the shelf's standing order:
                # "Dead letters go to default exchange with key 'documents_failed'"
                # Manager follows that rule automatically
            else:
                print(f"  ✅ Processed {body['doc_id']}")
                await message.ack() # Removes message (success, no DLQ)
        
        # Process one message
        # The manager wants to test if the "problem order shelf" (Dead Letter Queue) works by processing just ONE order.
        message=await main_q.get(fail=False) # fail=False =>  If no orders, just walk away (don't stand there waiting)
        if message:
            await process_with_failures(message)

        # Check DLQ
        await asyncio.sleep(0.5)
        dlq_message=await dlq.get(fail=False)
        if dlq_message:
            body=json.loads(dlq_message.body)
            print(f"  📬 DLQ contains failed message: {body['doc_id']}")
            await dlq_message.ack()

# ============================================================
# PRIORITY QUEUE — process urgent messages first
# ============================================================
async def demo_priority_queue():
    """
    Priority queues ensure critical work happens before regular work.
    P1 incidents processed before P3 — even if P3 was queued first.
    """
    print("\n=== Priority Queue ===")

    connection= await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel=await connection.channel()

        # Declare queue with max priority level 10
        priority_q=await channel.declare_queue(
            name="incidents_priority",
            durable=True,
            arguments={"x-max-priority":10}
        )

        # Send messages with different priorities
        # Lower number = lower priority (1=low, 10=critical)
        incidents=[
            (3,"P3: Slow query detected"),
            (10,"P1: Production database down"),
            (5,"P2:Memory leak detected"),
            (1,"P4:Minor UI change"),
            (10,"P1:Auth services 500 errors")
        ]

        for priority,message in incidents:
            await channel.default_exchange.publish(
                message=aio_pika.Message(
                    body=json.dumps({"message":message}).encode(),
                    priority=priority
                ),
                routing_key=priority_q.name
            )
            print(f"  → Queued (priority={priority}): {message}")

        print("\n  Reading in priority order:")
        for _ in range(5):
            meesage=await priority_q.get(fail=False)
            if meesage:
                body=json.loads(meesage.body)
                print(f"  ← Processing: {body['message']}")
                await meesage.ack()

# ============================================================
# REQUEST/REPLY PATTERN — RPC over RabbitMQ
# ============================================================
async def demo_request_reply():
    """
    RPC (Remote Procedure Call) pattern over RabbitMQ.
    Service A sends request, waits for reply from Service B.
    Useful when you need a result but want queue benefits.
    """
    print("\n=== Request/Reply (RPC) Pattern ===")

    connection=await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel=await connection.channel()

        # Create temporary exclusive reply queue
        # Only this connection can use it — deleted when connection closes
        callback_q=await channel.declare_queue(
            exclusive=True,
            auto_delete=True
        )

        correlation_id=str(uuid.uuid4())

        # A Future is like an empty promise ticket you hold at a pizza shop — you wait (await) for someone to fill it with your pizza (set_result), 
        # and your code stays paused until that happens, making async waiting clean and efficient.
        # Create an EMPTY promise box
        # response_future -> A box that will hold the result later
        # get_event_loop -> Creates empty box
        response_future:asyncio.Future=asyncio.get_event_loop().create_future()

        # Listen for reply
        async def on_reply(message:aio_pika.IncomingMessage):
            async with message.process():
                if message.correlation_id==correlation_id:
                    result=json.loads(message.body)
                    # Box now contains the answer!
                    response_future.set_result(result)

        await callback_q.consume(on_reply) # "I'm standing here, ready to receive"

        # Send request to Server example to the Openai server whos routing key is llm_rpc_request
        await channel.default_exchange.publish(
            message=aio_pika.Message(
                body=json.dumps({"prompt":"What is Langraph?"}).encode(),
                correlation_id=correlation_id,
                reply_to=callback_q.name,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key="llm_rpc_request"
        )
        print("  → Sent RPC request")

        # Simulate server processing the request
        # (in real life a separate worker does this)
        # Sending the response back to the queue through the routing key of queue name
        async def simulate_server():
            await asyncio.sleep(0.3)
            await channel.default_exchange.publish(
                message=aio_pika.Message(
                    body=json.dumps({"response":"LangGraph is a library for building stateful agents"}).encode(),
                    correlation_id=correlation_id
                ),
                routing_key=callback_q.name
                
            )
        
        await simulate_server()

        # Wait for reply (with timeout)
        try:
            result=await asyncio.wait_for(response_future,timeout=5.0)
            print(f"  ← Received reply: {result['response']}")
        except asyncio.TimeoutError:
            print("  ⏰ RPC timeout — server didn't respond")





async def main():
    print("=" * 50)
    print("RabbitMQ Basics")
    print("=" * 50)

    await basic_producer()
    await basic_consumer()
    await demo_exchanges()
    await demo_ded_letter_queue()
    await demo_priority_queue()
    await demo_request_reply()

if __name__=="__main__":
    asyncio.run(main())