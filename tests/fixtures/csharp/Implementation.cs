using MyWorldWorld;
using Host = MyWorldWorld.wit.Imports.neutral.provider.v0_4_0.IHostApiImports;
using Api = MyWorldWorld.wit.Exports.neutral.sampleApi.v1_2_3.INumberApiExports;

namespace MyWorldWorld
{
    public partial class MyWorldWorldExportsImpl : IMyWorldWorldExports
    {
        public static int AddNumber(int firstNumber, int secondNumber) => firstNumber + secondNumber;
    }
}

namespace MyWorldWorld.wit.Exports.neutral.sampleApi.v1_2_3
{
    public partial class NumberApiExportsImpl : INumberApiExports
    {
        private static uint dropped;
        public static uint DroppedCounters() => dropped;
        public static Api.Packet Roundtrip(Api.Packet value) => value;
        public static string? Maybe(string? value) => value;
        public static Result<string, string> Checked(string value) => value == "fail"
            ? Result<string, string>.Err("guest-error") : Result<string, string>.Ok(value);

        public static Result<Api.Packet, string> UseHost(Api.Packet value)
        {
            var answer = Host.Transform(new Host.HostPacket(value.text, value.bytes));
            return answer.IsOk
                ? Result<Api.Packet, string>.Ok(new Api.Packet(answer.AsOk.text, answer.AsOk.bytes))
                : Result<Api.Packet, string>.Err(answer.AsErr);
        }

        public static uint HostLifecycle(byte[] data)
        {
            using var iterator = new Host.Iterator(data);
            uint sum = 0;
            while (iterator.Next() is byte value) sum += value;
            return sum;
        }

        public class Counter : Api.Counter, Api.ICounter
        {
            private int value;
            public Counter(int initialValue) { value = initialValue; }
            public int Add(int delta) => value += delta;
            public int Get() => value;
            protected override void Dispose(bool disposing)
            {
                if (disposing) dropped++;
                base.Dispose(disposing);
            }
        }
    }
}
