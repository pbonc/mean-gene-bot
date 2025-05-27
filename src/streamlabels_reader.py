import os
import asyncio

LABELS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "labels"))

class StreamLabelsReader:
    def __init__(self, path=LABELS_DIR):
        self.path = path
        self.cache = {}

    def read_label_file(self, filename):
        try:
            with open(os.path.join(self.path, filename), "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return None

    def parse_top_list(self, filename, max_items=5):
        """
        Parse a top list file expected to have one item per line,
        format: 'username - amount'
        Returns list of tuples (username, amount)
        """
        try:
            path = os.path.join(self.path, filename)
            with open(path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
            results = []
            for line in lines[:max_items]:
                if " - " in line:
                    user, amount = line.split(" - ", 1)
                    results.append((user.strip(), amount.strip()))
                else:
                    results.append((line, None))
            return results
        except Exception:
            return []

    async def get_messages(self):
        """
        Return a list of ticker messages based on current label files.
        """
        msgs = []

        # Latest follower
        latest_follower = self.read_label_file("LatestFollower.txt")
        if latest_follower:
            msgs.append(f"👤 New follower: {latest_follower}")

        # Latest subscriber
        latest_sub = self.read_label_file("LatestSubscriber.txt")
        if latest_sub:
            msgs.append(f"🎉 New subscriber: {latest_sub}")

        # Latest gifted sub
        latest_gifted_sub = self.read_label_file("LatestGiftedSub.txt")
        if latest_gifted_sub:
            msgs.append(f"🎁 Gifted sub by: {latest_gifted_sub}")

        # Latest bits
        latest_bits = self.read_label_file("LatestBits.txt")
        if latest_bits:
            msgs.append(f"💎 Bits donated by: {latest_bits}")

        # Top 5 bits donors all-time
        top_bits = self.parse_top_list("TopBitsAllTime.txt")
        if top_bits:
            msg = "💎 Top Bits Donors: " + ", ".join(
                f"{user} ({amount})" if amount else user for user, amount in top_bits
            )
            msgs.append(msg)

        # Top 5 gifted subs all-time
        top_gifted_subs = self.parse_top_list("TopGiftedSubsAllTime.txt")
        if top_gifted_subs:
            msg = "🎁 Top Gifted Subs: " + ", ".join(
                f"{user} ({amount})" if amount else user for user, amount in top_gifted_subs
            )
            msgs.append(msg)

        # Recent subscriber count
        sub_count = self.read_label_file("SubscriberCount.txt")
        if sub_count:
            msgs.append(f"📈 Subscriber count: {sub_count}")

        # Recent follower count
        follower_count = self.read_label_file("FollowerCount.txt")
        if follower_count:
            msgs.append(f"📈 Follower count: {follower_count}")

        # Recent bits count
        bits_count = self.read_label_file("BitsCount.txt")
        if bits_count:
            msgs.append(f"📈 Bits total: {bits_count}")

        # If no messages, fallback
        if not msgs:
            msgs.append("📢 Welcome to the Darmunist News Network.")

        return msgs

# singleton instance for convenience
streamlabels_reader = StreamLabelsReader()

async def get_streamlabels_messages():
    return await streamlabels_reader.get_messages()
